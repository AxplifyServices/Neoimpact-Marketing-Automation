from __future__ import annotations

import hashlib
import json
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Dict, List, Optional, Tuple, Set

# lit automatiquement .env si présent
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from app.storage.runtime_db import RuntimeConnection, connect_runtime
from app.storage.postgres_db import get_column_names
from app.domain.canaux import resultats_for_canal
from app.domain.conversion_service import mark_converted, record_objective_entry
from app.best_channel.history import finalize_current_sequence, record_block_result_by_rid
from app.domain.send_time import normalize_creneau
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


# =========================================================
# Helpers DB / JSON / time
# =========================================================
def _connect() -> RuntimeConnection:
    return connect_runtime()


def _safe_json_loads(s: str, default: Any) -> Any:
    try:
        return json.loads(s)
    except Exception:
        return default


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _canon(s: str) -> str:
    return (s or "").strip()


def _payload_fingerprint(to_email: str, subject: str, body: str, id_action: str) -> str:
    """Empreinte fixe pour éviter de conserver les contenus Mail en mémoire."""
    payload = "\x1f".join((
        (to_email or "").strip().lower(),
        _canon(subject),
        _canon(body),
        (id_action or "").strip(),
    )).encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()


def _norm_str(x: Any) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    return "" if s.lower() == "none" else s


# =========================================================
# Credentials + SMTP (Gmail)
# =========================================================
def _get_credentials() -> Tuple[str, str]:
    sender = (os.environ.get("MAIL_SENDER") or "").strip()
    password = (os.environ.get("MAIL_PASSWORD") or "").strip()
    return sender, password


def _send_email(sender: str, password: str, to_email: str, subject: str, body: str) -> Tuple[bool, str]:
    try:
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = to_email
        msg["Subject"] = subject or ""
        msg.set_content(body or "")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.send_message(msg)

        return True, ""
    except Exception as e:
        return False, str(e)


# =========================================================
# Lecture contexte client + rendu
# =========================================================
def _get_client_context(conn: RuntimeConnection, radical_compte: str) -> Dict[str, str]:
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT radical_compte, Nom, Prenom, Mail
        FROM {CLIENTS_TABLE}
        WHERE radical_compte = ?
        """,
        (radical_compte,),
    )
    r = cur.fetchone()
    if not r:
        return {"radical_compte": radical_compte, "Nom": "", "Prenom": "", "Mail": ""}
    return dict(r)


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


def _render_template(text: str, ctx: Dict[str, str]) -> str:
    out = text or ""
    for k, v in (ctx or {}).items():
        out = out.replace("{" + k + "}", str(v or ""))
    return out


# =========================================================
# Récupération modèle pour une campagne
# =========================================================
def _get_id_modele_for_campagne(conn: RuntimeConnection, id_campagne: str) -> Optional[str]:
    cur = conn.cursor()
    cur.execute(
        f"SELECT id_modele FROM {CAMPAGNES_TABLE} WHERE id_campagne = ?",
        (id_campagne,),
    )
    r = cur.fetchone()
    if not r:
        return None
    return str(r["id_modele"])


def _get_liste_action_for_modele(conn: RuntimeConnection, id_modele: str) -> List[Dict[str, Any]]:
    cur = conn.cursor()

    cols = get_column_names(MODELES_TABLE)
    id_col = "id_modele" if "id_modele" in cols else ("ID_MODELE" if "ID_MODELE" in cols else "id_modele")

    cur.execute(
        f"SELECT liste_action FROM {MODELES_TABLE} WHERE {id_col} = ?",
        (id_modele,),
    )
    r = cur.fetchone()
    if not r:
        return []
    raw = r["liste_action"]
    if isinstance(raw, list):
        return raw
    data = _safe_json_loads(str(raw or ""), [])
    return data if isinstance(data, list) else []



# =========================================================
# Sous-action 1 : sélectionner les lignes candidates Mail (avec rowid unique)
# =========================================================
def _select_mail_candidates(
    conn: RuntimeConnection,
    limit_rows: int = 500,
    id_campagne: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Sélectionne un lot léger et, si demandé, isolé à une campagne."""
    cur = conn.cursor()
    campaign_clause = ""
    params: List[Any] = []
    campaign_id = _norm_str(id_campagne)
    if campaign_id:
        campaign_clause = "AND cc.ID_CAMPAGNE = ?"
        params.append(campaign_id)

    params.append(max(1, int(limit_rows)))
    cur.execute(
        f"""
        SELECT
            cc.rowid AS __rid,
            cc.ID_CAMPAGNE,
            cc.ID_Action,
            cc.Radical_compte
        FROM {CLIENTS_CAMPAGNES_TABLE} cc
        JOIN campagnes c ON c.id_campagne = cc.ID_CAMPAGNE
        WHERE COALESCE(cc.row_status,0) = 0
          AND COALESCE(c.etat_campagne,'') = 'En cours'
          AND COALESCE(cc.conversion, 0) <> 1
          AND COALESCE(cc.Canal,'') = 'Mail'
          AND COALESCE(cc.Action,'') IN ('Message', 'Mail')
          {campaign_clause}
        ORDER BY cc.rowid
        LIMIT ?
        """,
        params,
    )
    return [dict(r) for r in cur.fetchall()]


# =========================================================
# Sous-action 2 : construire le mail depuis le modèle (id_action)
# =========================================================
def _build_mail_for_row(conn: RuntimeConnection, row_cc: Dict[str, Any], liste_action: List[Dict[str, Any]]) -> Tuple[str, str, str]:
    radical = str(row_cc.get("Radical_compte") or "").strip()
    ctx = _get_client_context(conn, radical)
    to_email = (ctx.get("Mail") or "").strip()

    id_action = str(row_cc.get("ID_Action") or "").strip()
    bloc = find_bloc_by_id(liste_action, id_action) or {}

    subject = _render_template(str(bloc.get("Objet") or ""), ctx)
    body = _render_template(str(bloc.get("Contenu") or ""), ctx)

    return to_email, subject, body


# =========================================================
# Sous-action 3 : MAJ après mail (par rowid)
# =========================================================
def _update_after_mail_by_rid(conn: RuntimeConnection, rid: int, resultat: str, incr_mail: int, now_iso: str) -> None:
    cur = conn.cursor()
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
        ("Mail", resultat, now_iso, int(incr_mail), int(rid)),
    )
    record_block_result_by_rid(
        conn,
        int(rid),
        resultat=resultat,
        observed_at=now_iso,
    )


# =========================================================
# Sous-action 4 : avancer workflow (fils ou En attente) par rowid
# =========================================================
def _advance_workflow_after_mail_by_rid(
    conn: RuntimeConnection,
    rid: int,
    row_after: Dict[str, Any],
    liste_action: List[Dict[str, Any]],
) -> bool:
    """
    NEW:
    - Navigation via pick_next_child (support Parents / ConditionsByParent / objectif)
    - Si le bloc courant est objectif:
        * force Canal/Action='Objectif'
        * si branche Oui => conversion=1 (si colonne existe)
    - Si aucun next => Action='En attente'
    """
    row_after = _enrich_row_with_client_fields(conn, row_after)

    prev_action = _norm_str(row_after.get("Action"))
    prev_canal = _norm_str(row_after.get("Canal"))
    prev_id_action = _norm_str(row_after.get("ID_Action"))

    current_bloc = find_bloc_by_id(liste_action, prev_id_action)
    if not current_bloc:
        if prev_action == "En attente":
            return False
        cur = conn.cursor()
        cur.execute(f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET Action=? WHERE rowid=?", ("En attente", int(rid)))
        return True

    # 1) Si bloc objectif => afficher Objectif + conversion si Oui
    if is_objective_bloc(current_bloc):
        cur = conn.cursor()
        cur_id = _norm_str(current_bloc.get("ID")) or prev_id_action  # sécurité

        # ✅ UPDATE atomique : on synchronise ID_Action + Canal + Action ensemble
        cur.execute(
            f"""
            UPDATE {CLIENTS_CAMPAGNES_TABLE}
            SET ID_Action = ?, Canal = 'Objectif', Action = 'Objectif', "Creneau" = 'Indifferent'
            WHERE rowid = ?
            """,
            (cur_id, int(rid)),
        )

        # conversion=1 si branche Oui (si colonne existe)
        try:
            cols = set(get_column_names(CLIENTS_CAMPAGNES_TABLE))
        except Exception:
            cols = set()

        if "conversion" in cols:
            branch = objective_branch(current_bloc, row_after)
            if branch == "Non":
                finalize_current_sequence(
                    conn,
                    int(rid),
                    objective_validated=0,
                    objective_id_action=cur_id,
                )
                try:
                    from app.product_scoring.feedback import record_objective_feedback
                    record_objective_feedback(conn, int(rid), objective_id_action=cur_id, achieved=0)
                except Exception:
                    pass
            if branch == "Oui":
                mark_converted(
                    conn,
                    int(rid),
                    objective_id_action=cur_id,
                )
                conn.commit()
                # Conversion terminale : aucune navigation supplémentaire.
                return True

        conn.commit()

    # 2) Navigation NEW
    nxt = pick_next_child(liste_action, current_bloc, row_after)

    if not nxt:
        if prev_action == "En attente":
            return False
        cur = conn.cursor()
        cur.execute(f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET Action=? WHERE rowid=?", ("En attente", int(rid)))
        return True

    new_id = _norm_str(nxt.get("ID"))

    # si next est objectif => Canal/Action = Objectif
    if is_objective_bloc(nxt):
        record_objective_entry(
            conn,
            int(rid),
            source_id_action=prev_id_action,
            source_canal=prev_canal,
        )
        new_canal = "Objectif"
        new_action = "Objectif"
        new_creneau = "Indifferent"
    else:
        new_canal = _norm_str(nxt.get("Canal"))
        new_action = _norm_str(nxt.get("Action"))
        new_creneau = normalize_creneau(nxt.get("Creneau"))

    if not new_id or not new_action:
        if prev_action == "En attente":
            return False
        cur = conn.cursor()
        cur.execute(f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET Action=? WHERE rowid=?", ("En attente", int(rid)))
        return True

    if new_id == prev_id_action and new_canal == prev_canal and new_action == prev_action:
        return False

    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE {CLIENTS_CAMPAGNES_TABLE}
        SET ID_Action = ?, Canal = ?, Action = ?, "Creneau" = ?
        WHERE rowid = ?
        """,
        (new_id, new_canal, new_action, new_creneau, int(rid)),
    )
    return True




# =========================================================
# PASS : traite une passe de noeuds Mail
# =========================================================
def run_mail_pass(limit_rows: int = 500, seen_payloads: Optional[Set[str]] = None, id_campagne: Optional[str] = None) -> Dict[str, int]:
    if seen_payloads is None:
        seen_payloads = set()

    sender, password = _get_credentials()

    mail_results = resultats_for_canal("Mail")
    OK_LABEL = mail_results[0] if len(mail_results) >= 1 else "Transmis"
    KO_LABEL = mail_results[1] if len(mail_results) >= 2 else "Non transmis"

    stats = {
        "candidates": 0,
        "sent": 0,
        "skipped_duplicates": 0,
        "failed": 0,
        "rows_touched": 0,
        "workflow_changed": 0,
    }

    conn = _connect()
    try:
        cur = conn.cursor()

        candidates = _select_mail_candidates(conn, limit_rows=limit_rows, id_campagne=id_campagne)
        stats["candidates"] = len(candidates)
        if not candidates:
            return stats

        liste_action_cache: Dict[str, List[Dict[str, Any]]] = {}
        now = _now_iso()

        touched_rids: List[int] = []

        # phase 1 : envoi + MAJ mail
        for row_cc in candidates:
            rid = int(row_cc.get("__rid"))
            id_campagne = _norm_str(row_cc.get("ID_CAMPAGNE"))
            id_action = _norm_str(row_cc.get("ID_Action"))

            if not id_campagne:
                continue

            if id_campagne not in liste_action_cache:
                id_modele = _get_id_modele_for_campagne(conn, id_campagne) or ""
                liste_action_cache[id_campagne] = _get_liste_action_for_modele(conn, id_modele) if id_modele else []

            liste_action = liste_action_cache.get(id_campagne) or []

            to_email, subject, body = _build_mail_for_row(conn, row_cc, liste_action)

            if not to_email:
                _update_after_mail_by_rid(conn, rid, KO_LABEL, 0, now)
                stats["failed"] += 1
                stats["rows_touched"] += 1
                touched_rids.append(rid)
                continue

            key = _payload_fingerprint(to_email, subject, body, id_action)

            if key in seen_payloads:
                _update_after_mail_by_rid(conn, rid, OK_LABEL, 0, now)
                stats["skipped_duplicates"] += 1
                stats["rows_touched"] += 1
                touched_rids.append(rid)
                continue

            ok = False
            if sender and password:
                ok, _ = _send_email(sender, password, to_email, subject, body)
            else:
                ok = False

            if ok:
                seen_payloads.add(key)
                _update_after_mail_by_rid(conn, rid, OK_LABEL, 1, now)
                stats["sent"] += 1
            else:
                _update_after_mail_by_rid(conn, rid, KO_LABEL, 0, now)
                stats["failed"] += 1

            stats["rows_touched"] += 1
            touched_rids.append(rid)

        conn.commit()

        # phase 2 : avance workflow
        for rid in touched_rids:
            cur.execute(
                f"SELECT rowid AS __rid, * FROM {CLIENTS_CAMPAGNES_TABLE} WHERE rowid = ?",
                (int(rid),),
            )
            r = cur.fetchone()
            if not r:
                continue

            row_after = dict(r)
            id_campagne = _norm_str(row_after.get("ID_CAMPAGNE"))
            liste_action = liste_action_cache.get(id_campagne) or []
            changed = _advance_workflow_after_mail_by_rid(conn, rid, row_after, liste_action)

            if changed:
                stats["workflow_changed"] += 1

        conn.commit()
        return stats

    finally:
        conn.close()


# =========================================================
# META : boucle jusqu'à stabilisation
# =========================================================
def run_mail_meta_loop(max_passes: int = 20, limit_rows_per_pass: int = 500, id_campagne: Optional[str] = None) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "passes": 0,
        "total_candidates": 0,
        "total_sent": 0,
        "total_skipped_duplicates": 0,
        "total_failed": 0,
        "total_rows_touched": 0,
        "total_workflow_changed": 0,
        "stopped_reason": "",
        "pass_stats": [],
    }

    seen_payloads: Set[str] = set()

    for _ in range(int(max_passes)):
        stats = run_mail_pass(limit_rows=limit_rows_per_pass, seen_payloads=seen_payloads, id_campagne=id_campagne)

        summary["passes"] += 1
        summary["total_candidates"] += int(stats.get("candidates", 0))
        summary["total_sent"] += int(stats.get("sent", 0))
        summary["total_skipped_duplicates"] += int(stats.get("skipped_duplicates", 0))
        summary["total_failed"] += int(stats.get("failed", 0))
        summary["total_rows_touched"] += int(stats.get("rows_touched", 0))
        summary["total_workflow_changed"] += int(stats.get("workflow_changed", 0))
        summary["pass_stats"].append(stats)

        if int(stats.get("sent", 0)) == 0 and int(stats.get("workflow_changed", 0)) == 0:
            summary["stopped_reason"] = "stable_no_progress"
            break

        if int(stats.get("candidates", 0)) == 0:
            summary["stopped_reason"] = "no_candidates"
            break

    if not summary["stopped_reason"]:
        summary["stopped_reason"] = "max_passes_reached"

    return summary

# =========================================================
# API Outbound : un seul bloc Mail, sans boucle globale
# =========================================================
def prepare_mail_dispatch(
    id_campagne: str,
    radical_compte: str,
    block_id: str,
    occurrence: int,
) -> Dict[str, Any]:
    """Résout le payload Mail au dernier moment depuis le datamart courant."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT cc.rowid AS __rid, cc.ID_CAMPAGNE, cc.Radical_compte, cc.ID_Action,
                   cc.Canal, cc.Action, cc.Etat_campagne, cc.row_status, cc.conversion,
                   COALESCE(cc.action_execution_seq,0) AS action_execution_seq,
                   COALESCE(c.etat_campagne,'') AS campagne_master_etat
            FROM {CLIENTS_CAMPAGNES_TABLE} cc
            JOIN campagnes c ON c.id_campagne = cc.ID_CAMPAGNE
            WHERE cc.ID_CAMPAGNE=? AND cc.Radical_compte=?
            LIMIT 1
            """,
            (id_campagne, radical_compte),
        )
        row = cur.fetchone()
        if not row:
            return {"ok": False, "obsolete": True, "reason": "client_campagne_not_found"}
        cc = dict(row)
        if (
            int(cc.get("row_status") or 0) != 0
            or _norm_str(cc.get("campagne_master_etat")) != "En cours"
            or int(cc.get("conversion") or 0) == 1
        ):
            return {"ok": False, "obsolete": True, "reason": "campaign_or_client_inactive"}
        if _norm_str(cc.get("ID_Action")) != _norm_str(block_id) or int(cc.get("action_execution_seq") or 0) != int(occurrence):
            return {"ok": False, "obsolete": True, "reason": "workflow_moved"}
        if _norm_str(cc.get("Canal")) != "Mail" or _norm_str(cc.get("Action")) not in {"Message", "Mail"}:
            return {"ok": False, "obsolete": True, "reason": "not_mail_action"}

        id_modele = _get_id_modele_for_campagne(conn, id_campagne) or ""
        actions = _get_liste_action_for_modele(conn, id_modele) if id_modele else []
        to_email, subject, body = _build_mail_for_row(conn, cc, actions)
        sender, password = _get_credentials()
        if not to_email:
            return {"ok": False, "permanent": True, "reason": "missing_recipient"}
        if not sender or not password:
            return {"ok": False, "permanent": False, "reason": "mail_credentials_missing"}
        return {
            "ok": True,
            "rid": int(cc["__rid"]),
            "sender": sender,
            "password": password,
            "to_email": to_email,
            "subject": subject,
            "body": body,
        }
    finally:
        conn.close()


def send_mail_dispatch(payload: Dict[str, Any]) -> Tuple[bool, str]:
    return _send_email(
        _norm_str(payload.get("sender")),
        _norm_str(payload.get("password")),
        _norm_str(payload.get("to_email")),
        str(payload.get("subject") or ""),
        str(payload.get("body") or ""),
    )


def finalize_mail_dispatch(
    id_campagne: str,
    radical_compte: str,
    block_id: str,
    occurrence: int,
    *,
    delivered: bool,
) -> Dict[str, Any]:
    """Applique une seule fois le résultat Mail puis avance le workflow.

    La vérification bloc+occurrence rend la finalisation idempotente : un retry de
    finalisation après crash ne recompte pas un mail déjà appliqué.
    """
    mail_results = resultats_for_canal("Mail")
    ok_label = mail_results[0] if len(mail_results) >= 1 else "Transmis"
    ko_label = mail_results[1] if len(mail_results) >= 2 else "Non transmis"
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT rowid AS __rid, *
            FROM {CLIENTS_CAMPAGNES_TABLE}
            WHERE ID_CAMPAGNE=? AND Radical_compte=?
            FOR UPDATE
            """,
            (id_campagne, radical_compte),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            return {"ok": False, "obsolete": True, "reason": "client_campagne_not_found"}
        cc = dict(row)
        current_seq = int(cc.get("action_execution_seq") or 0)
        if _norm_str(cc.get("ID_Action")) != _norm_str(block_id) or current_seq != int(occurrence):
            conn.rollback()
            return {"ok": True, "already_applied": True}

        rid = int(cc["__rid"])
        _update_after_mail_by_rid(
            conn,
            rid,
            ok_label if delivered else ko_label,
            1 if delivered else 0,
            _now_iso(),
        )
        cur.execute(
            f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET action_execution_seq=COALESCE(action_execution_seq,0)+1 WHERE rowid=?",
            (rid,),
        )

        id_modele = _get_id_modele_for_campagne(conn, id_campagne) or ""
        actions = _get_liste_action_for_modele(conn, id_modele) if id_modele else []
        cur.execute(f"SELECT rowid AS __rid,* FROM {CLIENTS_CAMPAGNES_TABLE} WHERE rowid=?", (rid,))
        after = cur.fetchone()
        if after:
            _advance_workflow_after_mail_by_rid(conn, rid, dict(after), actions)
        conn.commit()
        return {"ok": True, "delivered": bool(delivered)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
