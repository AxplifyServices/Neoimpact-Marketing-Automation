from __future__ import annotations

import json
import os
import sqlite3
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Dict, List, Optional, Tuple

from app.storage.db import DB_PATH
from app.domain.canaux import compteur_for_canal

from app.domain.workflow_nav import (
    find_bloc_by_id,
    pick_next_child,
    is_objective_bloc,
    objective_branch,
)

CLIENTS_CAMPAGNES_TABLE = "clients_campagnes"
CAMPAGNES_TABLE = "campagnes"
MODELES_TABLE = "modeles"
CLIENTS_TABLE = "clients"


# =========================
# DB helpers
# =========================
def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def _safe_json_loads(s: str, default: Any) -> Any:
    try:
        return json.loads(s)
    except Exception:
        return default


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _norm_str(x: Any) -> str:
    return "" if x is None else str(x).strip()


# =========================
# Modèle : fetch liste_action + meta
# =========================
def _get_id_modele_for_campagne(conn: sqlite3.Connection, id_campagne: str) -> Optional[str]:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT id_modele FROM {CAMPAGNES_TABLE} WHERE id_campagne = ?", (id_campagne,))
    r = cur.fetchone()
    return _norm_str(r["id_modele"]) if r else None


def _get_liste_action_for_modele(conn: sqlite3.Connection, id_modele: str) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(f"PRAGMA table_info({MODELES_TABLE})")
    cols = [str(x[1]) for x in cur.fetchall()]
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
        cur.execute(f"PRAGMA table_info({queue_table})")
        qcols = [str(r[1]) for r in cur.fetchall()]
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
            "Etat_campagne": "COALESCE(cc.Etat_campagne,'')",
            # ⚠️ statut_* supprimés -> on ne les mappe plus
        }

        # build colonnes à insérer
        insert_cols = [c for c in select_map.keys() if c in qset]
        if not insert_cols:
            return

        insert_sql_cols = ", ".join(insert_cols)
        select_sql_cols = ", ".join([select_map[c] for c in insert_cols])

        cur.execute(
            f"""
            INSERT OR REPLACE INTO {queue_table} ({insert_sql_cols})
            SELECT
                {select_sql_cols}
            FROM {CLIENTS_CAMPAGNES_TABLE} cc
            LEFT JOIN {CLIENTS_TABLE} cl ON cl.radical_compte = cc.Radical_compte
            LEFT JOIN {CAMPAGNES_TABLE} c ON c.id_campagne = cc.ID_CAMPAGNE
            WHERE cc.ID_CAMPAGNE = ? AND cc.Radical_compte = ?
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


def _get_client_email(conn: sqlite3.Connection, radical_compte: str) -> str:
    conn.row_factory = sqlite3.Row
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
        conn.row_factory = sqlite3.Row
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
            row_after = dict(r2)

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
    """
    Bouton résultat (CRC/DA/CC):
    - MAJ clients_campagnes:
        Resultat_last_action = bouton
        Last_action = Action actuelle (avant changement)
        Date_last_action = now
        incr compteur selon Canal
    - si objectif atteint -> Closed
    - navigation graphe (fils):
        si condition ok -> ID_Action/Canal/Action = noeud fils
        sinon -> Action='En attente'
    - supprime la ligne de la queue
    - route immédiat (queues ou mail)
    """
    id_campagne = _norm_str(row.get("ID_CAMPAGNE"))
    radical = _norm_str(row.get("Radical_compte"))

    if not id_campagne or not radical:
        return {"ok": False, "error": "missing_keys"}

    now = _now_iso()

    conn = _connect()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute(
            f"SELECT rowid as __rid, * FROM {CLIENTS_CAMPAGNES_TABLE} WHERE ID_CAMPAGNE=? AND Radical_compte=?",
            (id_campagne, radical),
        )
        r = cur.fetchone()
        if not r:
            cur.execute(f"DELETE FROM {queue_table} WHERE ID_CAMPAGNE=? AND Radical_compte=?", (id_campagne, radical))
            conn.commit()
            return {"ok": False, "error": "client_campagne_not_found"}

        cc = dict(r)
        rid = int(cc["__rid"])
        canal = _norm_str(cc.get("Canal"))
        action_actuelle = _norm_str(cc.get("Action"))

        # compteur selon canal
        compteur_col = compteur_for_canal(canal) or ""
        incr_sql = f", {compteur_col} = COALESCE({compteur_col},0) + 1" if compteur_col else ""

        sql = f"""
            UPDATE {CLIENTS_CAMPAGNES_TABLE}
            SET
                Resultat_last_action = ?,
                Last_action = ?,
                Date_last_action = ?
                {incr_sql}
            WHERE rowid = ?
        """
        params: List[Any] = [resultat_label, action_actuelle, now, rid]
        cur.execute(sql, params)
        conn.commit()

        # charger modèle
        id_modele = _get_id_modele_for_campagne(conn, id_campagne) or ""
        liste_action = _get_liste_action_for_modele(conn, id_modele) if id_modele else []

        # re-read
        cur.execute(f"SELECT rowid as __rid, * FROM {CLIENTS_CAMPAGNES_TABLE} WHERE rowid=?", (rid,))
        r2 = cur.fetchone()
        if not r2:
            return {"ok": False, "error": "row_missing_after_update"}
        row_after = dict(r2)

        # navigation fils (NEW)
        current = find_bloc_by_id(liste_action, _norm_str(row_after.get("ID_Action")))
        nxt = pick_next_child(liste_action, current, row_after) if current else None

        if not nxt:
            cur.execute(f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET Action=? WHERE rowid=?", ("En attente", rid))
            conn.commit()
        else:
            new_id = _norm_str(nxt.get("ID"))

            if is_objective_bloc(nxt):
                new_canal = "Objectif"
                new_action = "Objectif"
            else:
                new_canal = _norm_str(nxt.get("Canal"))
                new_action = _norm_str(nxt.get("Action"))

            if not new_id or not new_action:
                cur.execute(f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET Action=? WHERE rowid=?", ("En attente", rid))
                conn.commit()
            else:
                cur.execute(
                    f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET ID_Action=?, Canal=?, Action=? WHERE rowid=?",
                    (new_id, new_canal, new_action, rid),
                )
                conn.commit()


        # suppression queue
        cur.execute(f"DELETE FROM {queue_table} WHERE ID_CAMPAGNE=? AND Radical_compte=?", (id_campagne, radical))
        conn.commit()

    finally:
        conn.close()

    # routage immédiat
    return route_after_update(id_campagne, radical)


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
        conn.row_factory = sqlite3.Row
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
        # NEW: un bloc objectif est une "gate" -> pas de routage queue/mail
        if canal == "Objectif" or action == "Objectif":
            return {"ok": True, "routed_to": "none", "action": action, "canal": canal}

    finally:
        conn.close()

    if action == "Appeler":
        _append_one_to_queue("crc_input", id_campagne, radical_compte)
        return {"ok": True, "routed_to": "crc_input"}

    if action == "Directeur d'agence":
        _append_one_to_queue("vers_da", id_campagne, radical_compte)
        return {"ok": True, "routed_to": "vers_da"}

    if action == "Conseiller client":
        _append_one_to_queue("vers_cc", id_campagne, radical_compte)
        return {"ok": True, "routed_to": "vers_cc"}

    if _is_mail_node(canal, action):
        mail_summary = _send_mail_for_one_client_and_advance(id_campagne, radical_compte, max_steps=10)
        post = route_after_update(id_campagne, radical_compte)
        return {"ok": True, "routed_to": "mail", "mail": mail_summary, "post_mail": post}

    return {"ok": True, "routed_to": "none", "action": action, "canal": canal}
