from __future__ import annotations

import json
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Dict, List, Optional, Tuple

from app.storage.runtime_db import RuntimeConnection, connect_runtime
from app.storage.postgres_db import get_column_names, table_exists
from app.domain.canaux import compteur_for_canal
from app.domain.conversion_service import record_objective_entry

from app.domain.workflow_nav import (
    find_bloc_by_id,
    pick_next_child,
    is_objective_bloc,
    objective_branch,
)

from app.domain.terrain_visit_webhook import send_visit_for_client

CLIENTS_CAMPAGNES_TABLE = "clients_campagnes"
CAMPAGNES_TABLE = "campagnes"
MODELES_TABLE = "modeles"
CLIENTS_TABLE = "clients"


# =========================
# DB helpers
# =========================
def _connect() -> RuntimeConnection:
    return connect_runtime()


def _table_exists(conn: RuntimeConnection, table: str) -> bool:
    return table_exists(str(table or "").strip())


def _safe_json_loads(s: str, default: Any) -> Any:
    try:
        return json.loads(s)
    except Exception:
        return default


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _norm_str(x: Any) -> str:
    return "" if x is None else str(x).strip()


def _enrich_row_with_client_fields(
    conn: RuntimeConnection,
    row_cc: Dict[str, Any],
) -> Dict[str, Any]:
    """Ajoute clients.* et client.<colonne> au contexte de navigation."""
    radical = _norm_str(
        row_cc.get("Radical_compte")
        or row_cc.get("radical_compte")
    )
    if not radical:
        return row_cc

    cur = conn.cursor()
    cur.execute(
        f"SELECT * FROM {CLIENTS_TABLE} WHERE radical_compte = ? LIMIT 1",
        (radical,),
    )
    client = cur.fetchone()
    if not client:
        return row_cc

    for key, value in dict(client).items():
        row_cc.setdefault(str(key), value)
        row_cc.setdefault(f"client.{key}", value)

    return row_cc


# =========================
# Modèle : fetch liste_action + meta
# =========================
def _get_id_modele_for_campagne(conn: RuntimeConnection, id_campagne: str) -> Optional[str]:
    cur = conn.cursor()
    cur.execute(f"SELECT id_modele FROM {CAMPAGNES_TABLE} WHERE id_campagne = ?", (id_campagne,))
    r = cur.fetchone()
    return _norm_str(r["id_modele"]) if r else None

def _get_type_campagne_for_campagne(conn: RuntimeConnection, id_campagne: str) -> str:
    cur = conn.cursor()
    cur.execute(
        f"SELECT type_campagne FROM {CAMPAGNES_TABLE} WHERE id_campagne = ?",
        (id_campagne,),
    )
    r = cur.fetchone()
    val = _norm_str(r["type_campagne"]) if r and "type_campagne" in r.keys() else ""
    return val or "sans_action_terrain"


def _get_liste_action_for_modele(conn: RuntimeConnection, id_modele: str) -> List[Dict[str, Any]]:
    cur = conn.cursor()

    cols = get_column_names(MODELES_TABLE)
    id_col = "id_modele" if "id_modele" in cols else ("ID_MODELE" if "ID_MODELE" in cols else "id_modele")

    cur.execute(f"SELECT liste_action FROM {MODELES_TABLE} WHERE {id_col} = ?", (id_modele,))
    r = cur.fetchone()
    if not r:
        return []
    raw = r["liste_action"]
    if isinstance(raw, list):
        return raw
    data = _safe_json_loads(_norm_str(raw), [])
    return data if isinstance(data, list) else []


# =========================
# Queue append (CRC/DA/CC)
# =========================
def _append_one_to_queue(queue_table: str, id_campagne: str, radical_compte: str) -> None:
    """
    Insert OR REPLACE dans la queue à partir de clients_campagnes (1 seule ligne).
    Version robuste: n'insère que les colonnes réellement présentes dans la queue.
    """
    conn = _connect()
    try:
        if not _table_exists(conn, queue_table):
            return

        cur = conn.cursor()

        # colonnes réelles de la queue
        qcols = get_column_names(queue_table)
        qset = set(qcols)

        # mapping colonne -> expression SQL SELECT
        select_map = {
            "ID_CAMPAGNE": "cc.ID_CAMPAGNE",
            "Radical_compte": "cc.Radical_compte",
            "Numero_Tel": "cl.Numero_Tel",
            "Mail": "cl.Mail",
            "date_creation_campagne": "COALESCE(c.date_debut,'')",
            "date_last_action": """
                CASE
                    WHEN TRIM(COALESCE(cc.arriv_eche,'')) = 'Oui' THEN '0000-01-01 00:00:00'
                    ELSE COALESCE(cc.Date_last_action,'')
                END
            """,
            "ID_Action": "COALESCE(cc.ID_Action,'')",
            "Canal": "COALESCE(cc.Canal,'')",
            "Action": "COALESCE(cc.Action,'')",
            "Etat_campagne": "COALESCE(c.etat_campagne,'')",
            # ⚠️ statut_* supprimés -> on ne les mappe plus
        }

        # build colonnes à insérer
        insert_cols = [c for c in select_map.keys() if c in qset]
        if not insert_cols:
            return

        insert_sql_cols = ", ".join(insert_cols)
        select_sql_cols = ", ".join([select_map[c] for c in insert_cols])

        update_cols = [
            c
            for c in insert_cols
            if c not in {"ID_CAMPAGNE", "Radical_compte"}
        ]
        if update_cols:
            conflict_sql = "DO UPDATE SET " + ", ".join(
                f"{c} = EXCLUDED.{c}"
                for c in update_cols
            )
        else:
            conflict_sql = "DO NOTHING"

        cur.execute(
            f"""
            INSERT INTO {queue_table} ({insert_sql_cols})
            SELECT
                {select_sql_cols}
            FROM {CLIENTS_CAMPAGNES_TABLE} cc
            LEFT JOIN {CLIENTS_TABLE} cl ON cl.radical_compte = cc.Radical_compte
            LEFT JOIN {CAMPAGNES_TABLE} c ON c.id_campagne = cc.ID_CAMPAGNE
            WHERE cc.ID_CAMPAGNE = ? AND cc.Radical_compte = ?
            ON CONFLICT (ID_CAMPAGNE, Radical_compte)
            {conflict_sql}
            """,
            (id_campagne, radical_compte),
        )
        conn.commit()
    finally:
        conn.close()



# =========================
# Mail (1 ligne) : SMTP + avancée workflow
# =========================
def _is_mail_node(canal: str, action: str) -> bool:
    c = _norm_str(canal)
    a = _norm_str(action)
    return (c == "Mail") and (a in ("Mail", "Message"))


def _get_mail_credentials() -> Tuple[str, str]:
    sender = (os.environ.get("MAIL_SENDER") or "").strip()
    password = (os.environ.get("MAIL_PASSWORD") or "").strip()
    return sender, password


def _send_mail(sender: str, password: str, to_email: str, subject: str, body: str) -> bool:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject or ""
    msg.set_content(body or "")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)

    return True


def _get_client_email(conn: RuntimeConnection, radical_compte: str) -> str:
    cur = conn.cursor()
    cur.execute(f"SELECT Mail FROM {CLIENTS_TABLE} WHERE radical_compte = ?", (radical_compte,))
    r = cur.fetchone()
    return _norm_str(r["Mail"]) if r else ""


def _render_template(text: str, ctx: Dict[str, Any]) -> str:
    out = text or ""
    for k, v in (ctx or {}).items():
        out = out.replace("{" + str(k) + "}", str(v or ""))
    return out


def _send_mail_for_one_client_and_advance(id_campagne: str, radical_compte: str, max_steps: int = 10) -> Dict[str, Any]:
    """
    Traite UNIQUEMENT cette ligne si elle est sur un noeud Mail, et avance le graphe.
    Utilise workflow_nav pour la sélection des fils.
    """
    sender, password = _get_mail_credentials()
    summary = {"steps": 0, "sent": 0, "failed": 0, "stopped_reason": "", "last_action": ""}

    conn = _connect()
    try:
        cur = conn.cursor()

        id_modele = _get_id_modele_for_campagne(conn, id_campagne) or ""
        liste_action = _get_liste_action_for_modele(conn, id_modele) if id_modele else []

        for _ in range(int(max_steps)):
            cur.execute(
                f"SELECT rowid as __rid, * FROM {CLIENTS_CAMPAGNES_TABLE} WHERE ID_CAMPAGNE=? AND Radical_compte=?",
                (id_campagne, radical_compte),
            )
            r = cur.fetchone()
            if not r:
                summary["stopped_reason"] = "row_not_found"
                break

            row_cc = dict(r)
            rid = int(row_cc["__rid"])

            try:
                if int(row_cc.get("conversion") or 0) == 1:
                    summary["stopped_reason"] = "converted"
                    break
            except Exception:
                pass

            canal = _norm_str(row_cc.get("Canal"))
            action = _norm_str(row_cc.get("Action"))
            if not _is_mail_node(canal, action):
                summary["stopped_reason"] = "not_mail_node"
                break

            id_action = _norm_str(row_cc.get("ID_Action"))
            bloc = find_bloc_by_id(liste_action, id_action) or {}
            subject = _norm_str(bloc.get("Objet"))
            body = _norm_str(bloc.get("Contenu"))

            ctx = {"radical_compte": radical_compte}
            subject = _render_template(subject, ctx)
            body = _render_template(body, ctx)

            to_email = _get_client_email(conn, radical_compte)

            ok = False
            if sender and password and to_email:
                try:
                    ok = _send_mail(sender, password, to_email, subject, body)
                except Exception:
                    ok = False

            resultat = "Transmis" if ok else "Non transmis"
            now = _now_iso()

            cur.execute(
                f"""
                UPDATE {CLIENTS_CAMPAGNES_TABLE}
                SET
                    Last_action = ?,
                    Resultat_last_action = ?,
                    Date_last_action = ?,
                    NB_jour_last_action = 0,
                    arriv_eche = 'Non',
                    NB_mail = COALESCE(NB_mail,0) + ?
                WHERE rowid = ?
                """,
                ("Mail", resultat, now, 1 if ok else 0, rid),
            )
            conn.commit()

            summary["steps"] += 1
            summary["sent"] += 1 if ok else 0
            summary["failed"] += 0 if ok else 1
            summary["last_action"] = "Mail"

            # re-fetch après update
            cur.execute(f"SELECT rowid as __rid, * FROM {CLIENTS_CAMPAGNES_TABLE} WHERE rowid=?", (rid,))
            r2 = cur.fetchone()
            if not r2:
                summary["stopped_reason"] = "row_missing_after_update"
                break
            row_after = _enrich_row_with_client_fields(conn, dict(r2))

            current = find_bloc_by_id(liste_action, _norm_str(row_after.get("ID_Action")))
            if not current:
                cur.execute(f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET Action=? WHERE rowid=?", ("En attente", rid))
                conn.commit()
                summary["stopped_reason"] = "bloc_not_found"
                break

            nxt = pick_next_child(liste_action, current, row_after)
            if not nxt:
                cur.execute(f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET Action=? WHERE rowid=?", ("En attente", rid))
                conn.commit()
                summary["stopped_reason"] = "no_child_match"
                break

            new_id = _norm_str(nxt.get("ID"))

            # si next est un bloc objectif -> on force Canal/Action
            if is_objective_bloc(nxt):
                record_objective_entry(
                    conn,
                    rid,
                    source_id_action=id_action,
                    source_canal=canal,
                )
                new_canal = "Objectif"
                new_action = "Objectif"
            else:
                new_canal = _norm_str(nxt.get("Canal"))
                new_action = _norm_str(nxt.get("Action"))


            if not new_id or not new_action:
                cur.execute(f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET Action=? WHERE rowid=?", ("En attente", rid))
                conn.commit()
                summary["stopped_reason"] = "invalid_child"
                break

            cur.execute(
                f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET ID_Action=?, Canal=?, Action=? WHERE rowid=?",
                (new_id, new_canal, new_action, rid),
            )
            conn.commit()

            if not _is_mail_node(new_canal, new_action):
                summary["stopped_reason"] = "mail_chain_completed"
                break

        if not summary["stopped_reason"]:
            summary["stopped_reason"] = "max_steps_reached"

        return summary

    finally:
        conn.close()


# =========================
# Public API : résultat depuis une queue
# =========================
def apply_result_from_queue(row: Dict[str, Any], resultat_label: str, queue_table: str) -> Dict[str, Any]:
    """Applique un résultat de canal et avance le workflow.

    `outbound_dispatches` est la source générique des callbacks externes depuis
    la migration 010. `external_visit_dispatches` reste accepté uniquement pour
    compatibilité avec les visites historiques déjà émises.
    """
    id_campagne = _norm_str(row.get("ID_CAMPAGNE"))
    radical = _norm_str(row.get("Radical_compte"))
    block_id = _norm_str(row.get("ID_Action"))
    if not id_campagne or not radical or not block_id:
        return {"ok": False, "error": "missing_keys"}

    now = _now_iso()
    generic_external = queue_table == "outbound_dispatches"
    legacy_external = queue_table == "external_visit_dispatches"
    external = generic_external or legacy_external

    conn = _connect()
    try:
        cur = conn.cursor()

        dispatch_id = None
        if generic_external:
            cur.execute(
                """
                SELECT id,status
                FROM outbound_dispatches
                WHERE id_campagne=? AND radical_compte=? AND block_id=?
                  AND channel='TERRAIN'
                ORDER BY occurrence DESC,id DESC
                LIMIT 1
                FOR UPDATE
                """,
                (id_campagne, radical, block_id),
            )
            dispatch_row = cur.fetchone()
            if not dispatch_row:
                conn.rollback()
                return {"ok": False, "error": "dispatch_not_found"}
            dispatch_id = int(dispatch_row["id"])
            dispatch_status = _norm_str(dispatch_row.get("status"))
            if dispatch_status == "completed":
                conn.rollback()
                return {"ok": False, "error": "dispatch_already_completed"}
            if dispatch_status not in {"waiting_callback", "sent"}:
                conn.rollback()
                return {"ok": False, "error": "dispatch_not_pending", "status": dispatch_status}
        elif legacy_external:
            cur.execute(
                """
                SELECT id,status FROM external_visit_dispatches
                WHERE id_campagne=? AND radical_compte=? AND block_id=?
                FOR UPDATE
                """,
                (id_campagne, radical, block_id),
            )
            dispatch_row = cur.fetchone()
            if not dispatch_row:
                conn.rollback()
                return {"ok": False, "error": "dispatch_not_found"}
            dispatch_status = _norm_str(dispatch_row.get("status"))
            if dispatch_status != "sent":
                conn.rollback()
                return {"ok": False, "error": "dispatch_not_pending", "status": dispatch_status}

        cur.execute(
            f"""
            SELECT rowid AS __rid,*
            FROM {CLIENTS_CAMPAGNES_TABLE}
            WHERE ID_CAMPAGNE=? AND Radical_compte=? AND ID_Action=?
            FOR UPDATE
            """,
            (id_campagne, radical, block_id),
        )
        r = cur.fetchone()
        if not r:
            if generic_external and dispatch_id is not None:
                cur.execute(
                    "UPDATE outbound_dispatches SET status='obsolete',last_error='callback_not_matched',completed_at=NOW(),updated_at=NOW() WHERE id=?",
                    (dispatch_id,),
                )
            elif legacy_external:
                cur.execute(
                    "UPDATE external_visit_dispatches SET status='callback_not_matched' WHERE id_campagne=? AND radical_compte=? AND block_id=?",
                    (id_campagne, radical, block_id),
                )
            elif not external:
                cur.execute(f"DELETE FROM {queue_table} WHERE ID_CAMPAGNE=? AND Radical_compte=?", (id_campagne, radical))
            conn.commit()
            return {"ok": False, "error": "client_campagne_not_found_or_not_on_this_block"}

        cc = dict(r)
        rid = int(cc["__rid"])
        canal = _norm_str(cc.get("Canal"))
        action_actuelle = _norm_str(cc.get("Action"))
        if int(cc.get("conversion") or 0) == 1:
            if generic_external and dispatch_id is not None:
                cur.execute(
                    "UPDATE outbound_dispatches SET status='completed',completed_at=NOW(),last_error='callback_ignored_converted',updated_at=NOW() WHERE id=?",
                    (dispatch_id,),
                )
            elif legacy_external:
                cur.execute(
                    "UPDATE external_visit_dispatches SET status='callback_ignored_converted' WHERE id_campagne=? AND radical_compte=? AND block_id=?",
                    (id_campagne, radical, block_id),
                )
            conn.commit()
            return {"ok": False, "error": "client_already_converted"}

        compteur_col = compteur_for_canal(canal) or ""
        incr_parts: List[str] = ["action_execution_seq = COALESCE(action_execution_seq,0) + 1"]
        if compteur_col:
            incr_parts.append(f"{compteur_col} = COALESCE({compteur_col},0) + 1")
        if canal in ("Directeur d'agence", "Conseiller client"):
            incr_parts.append("NB_approche_commercial = COALESCE(NB_approche_commercial,0) + 1")
        incr_sql = ", " + ", ".join(incr_parts)
        cur.execute(
            f"""
            UPDATE {CLIENTS_CAMPAGNES_TABLE}
            SET Resultat_last_action=?, Last_action=?, Date_last_action=?,
                NB_jour_last_action=0, arriv_eche='Non' {incr_sql}
            WHERE rowid=?
            """,
            (resultat_label, action_actuelle, now, rid),
        )

        id_modele = _get_id_modele_for_campagne(conn, id_campagne) or ""
        liste_action = _get_liste_action_for_modele(conn, id_modele) if id_modele else []
        cur.execute(f"SELECT rowid AS __rid,* FROM {CLIENTS_CAMPAGNES_TABLE} WHERE rowid=?", (rid,))
        r2 = cur.fetchone()
        if not r2:
            conn.rollback()
            return {"ok": False, "error": "row_missing_after_update"}
        row_after = _enrich_row_with_client_fields(conn, dict(r2))
        current = find_bloc_by_id(liste_action, _norm_str(row_after.get("ID_Action")))
        nxt = pick_next_child(liste_action, current, row_after) if current else None
        if not nxt:
            cur.execute(f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET Action=? WHERE rowid=?", ("En attente", rid))
        else:
            new_id = _norm_str(nxt.get("ID"))
            if is_objective_bloc(nxt):
                record_objective_entry(
                    conn,
                    rid,
                    source_id_action=_norm_str(row_after.get("ID_Action")),
                    source_canal=_norm_str(row_after.get("Canal")),
                )
                new_canal, new_action = "Objectif", "Objectif"
            else:
                new_canal = _norm_str(nxt.get("Canal"))
                new_action = _norm_str(nxt.get("Action"))
            if not new_id or not new_action:
                cur.execute(f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET Action=? WHERE rowid=?", ("En attente", rid))
            else:
                cur.execute(
                    f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET ID_Action=?,Canal=?,Action=? WHERE rowid=?",
                    (new_id, new_canal, new_action, rid),
                )

        if generic_external and dispatch_id is not None:
            cur.execute(
                "UPDATE outbound_dispatches SET status='completed',completed_at=NOW(),last_error=NULL,updated_at=NOW() WHERE id=? AND status IN ('waiting_callback','sent')",
                (dispatch_id,),
            )
        elif legacy_external:
            cur.execute(
                "UPDATE external_visit_dispatches SET status='callback_received' WHERE id_campagne=? AND radical_compte=? AND block_id=?",
                (id_campagne, radical, block_id),
            )
        elif not external:
            cur.execute(f"DELETE FROM {queue_table} WHERE ID_CAMPAGNE=? AND Radical_compte=?", (id_campagne, radical))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return route_after_update(id_campagne, radical)

def _resolve_queue_for_action(action: str, type_campagne: str) -> str:
    action = _norm_str(action)
    type_campagne = _norm_str(type_campagne) or "sans_action_terrain"

    if action == "Appeler":
        return "crc_input"

    if action == "Directeur d'agence":
        return "" if type_campagne == "avec_action_terrain" else "vers_da"

    if action == "Conseiller client":
        return "" if type_campagne == "avec_action_terrain" else "vers_cc"

    return ""

def route_after_update(id_campagne: str, radical_compte: str) -> Dict[str, Any]:
    """
    Après MAJ clients_campagnes:
    - Appeler -> crc_input
    - Directeur d'agence -> vers_da
    - Conseiller client -> vers_cc
    - Mail -> exécuter mail (chain) puis re-router
    """
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT * FROM {CLIENTS_CAMPAGNES_TABLE} WHERE ID_CAMPAGNE=? AND Radical_compte=?",
            (id_campagne, radical_compte),
        )
        r = cur.fetchone()
        if not r:
            return {"ok": False, "error": "client_campagne_not_found_after"}
        cc = dict(r)
        canal = _norm_str(cc.get("Canal"))
        action = _norm_str(cc.get("Action"))
        type_campagne = _get_type_campagne_for_campagne(conn, id_campagne)

        try:
            if int(cc.get("conversion") or 0) == 1:
                return {
                    "ok": True,
                    "routed_to": "none",
                    "terminal": "conversion",
                    "action": action,
                    "canal": canal,
                }
        except Exception:
            pass

        # Un bloc objectif est une gate -> pas de routage queue/mail
        if canal == "Objectif" or action == "Objectif":
            return {"ok": True, "routed_to": "none", "action": action, "canal": canal}

    finally:
        conn.close()

    if type_campagne == "avec_action_terrain" and action in ("Directeur d'agence", "Conseiller client"):
        from app.outbound.store import enqueue_single
        dispatch = enqueue_single(id_campagne, radical_compte, channel="TERRAIN")
        return {"ok": bool(dispatch.get("ok")), "routed_to": "outbound:TERRAIN", "dispatch": dispatch}

    queue_name = _resolve_queue_for_action(action, type_campagne)
    if queue_name:
        _append_one_to_queue(queue_name, id_campagne, radical_compte)
        return {"ok": True, "routed_to": queue_name}

    if _is_mail_node(canal, action):
        from app.outbound.store import enqueue_single
        dispatch = enqueue_single(id_campagne, radical_compte, channel="MAIL")
        return {"ok": bool(dispatch.get("ok")), "routed_to": "outbound:MAIL", "dispatch": dispatch}

    return {"ok": True, "routed_to": "none", "action": action, "canal": canal}

