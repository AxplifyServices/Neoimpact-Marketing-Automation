# app/scripts/batch_manuel.py
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from app.storage.db import DB_PATH
from app.storage.campagnes_store_sqlite import list_all_campagnes, update_etat
from app.storage.clients_campagnes_store_sqlite import (
    ensure_table as ensure_clients_campagnes,
    set_clients_etat_for_campagne,
)

# outputs (phase 1)
from app.storage.crc_input_store_sqlite import ensure_crc_input_table, clear_crc_input, fill_crc_input_from_clients_campagnes
from app.storage.action_vers_da_store_sqlite import ensure_vers_da_table, fill_action_vers_da_from_clients_campagnes
from app.storage.action_vers_cc_store_sqlite import ensure_vers_cc_table, fill_action_vers_cc_from_clients_campagnes

from app.engine.traitement_mail_engine import run_mail_meta_loop
from app.domain.workflow_nav import objective_reached, find_bloc_by_id, pick_next_child


CLIENTS_CAMPAGNES_TABLE = "clients_campagnes"
CAMPAGNES_TABLE = "campagnes"
MODELES_TABLE = "modeles"
CLIENTS_TABLE = "clients"


# =========================================================
# Helpers
# =========================================================
def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _norm_str(x: Any) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    return "" if s.lower() == "none" else s


def _norm_cmp(x: Any) -> str:
    s = _norm_str(x).lower()
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_iso_date(x: Any) -> Optional[date]:
    t = _norm_str(x)
    if not t:
        return None
    try:
        return date.fromisoformat(t[:10])
    except Exception:
        return None


def _safe_json_loads(s: str, default: Any) -> Any:
    try:
        return json.loads(s)
    except Exception:
        return default


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clients_columns(conn: sqlite3.Connection) -> List[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({CLIENTS_TABLE})")
    return [r[1] for r in cur.fetchall()]


def _resolve_clients_col(conn: sqlite3.Connection, requested_col: str) -> Optional[str]:
    """
    Résout une colonne de la table clients de manière robuste:
    - match exact
    - sinon match insensible à la casse/accents/espaces via _norm_cmp
    Retourne le NOM réel de la colonne dans la DB (à utiliser dans le SQL).
    """
    req = _norm_str(requested_col)
    if not req:
        return None

    cols = _clients_columns(conn)
    # 1) exact
    if req in cols:
        return req

    # 2) normalized compare
    req_n = _norm_cmp(req)
    for c in cols:
        if _norm_cmp(c) == req_n:
            return c

    return None


def _modeles_id_col(conn: sqlite3.Connection) -> str:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({MODELES_TABLE})")
    cols = [r[1] for r in cur.fetchall()]
    if "id_modele" in cols:
        return "id_modele"
    if "ID_MODELE" in cols:
        return "ID_MODELE"
    return "id_modele"


# =========================================================
# Batch steps (ordre imposé)
# =========================================================
def _list_active_campaigns(campagnes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for c in campagnes:
        etat = _norm_str(c.get("etat") or c.get("etat_campagne"))
        if etat in ("En cours", "Planifiée", "En pause"):
            out.append(c)
    return out


def _load_modele_meta(conn: sqlite3.Connection, id_modele: str) -> Tuple[str, str, List[Dict[str, Any]]]:
    id_col = _modeles_id_col(conn)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT variable_cible, objectif, liste_action FROM {MODELES_TABLE} WHERE {id_col} = ?", (id_modele,))
    r = cur.fetchone()
    if not r:
        return "", "", []
    variable_cible = _norm_str(r["variable_cible"])
    objectif = _norm_str(r["objectif"])
    raw = r["liste_action"]
    if isinstance(raw, list):
        liste_action = raw
    else:
        liste_action = _safe_json_loads(_norm_str(raw), [])
        if not isinstance(liste_action, list):
            liste_action = []
    return variable_cible, objectif, liste_action


def _update_statut_actuel_from_clients(conn: sqlite3.Connection, id_campagne: str, variable_cible: str) -> int:
    """
    Met à jour clients_campagnes.statut_actuel depuis clients.<variable_cible>.
    Fix: résolution de colonne clients en case-insensitive (évite les var = 'statut_client' vs 'STATUT_CLIENT').
    """
    var = _norm_str(variable_cible)
    if not var:
        return 0

    resolved_col = _resolve_clients_col(conn, var)
    if not resolved_col:
        return 0

    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE {CLIENTS_CAMPAGNES_TABLE}
        SET statut_actuel = (
            SELECT COALESCE(cl."{resolved_col}", '')
            FROM {CLIENTS_TABLE} cl
            WHERE cl.radical_compte = {CLIENTS_CAMPAGNES_TABLE}.Radical_compte
        )
        WHERE ID_CAMPAGNE = ?
          AND COALESCE(Etat_campagne,'') IN ('En cours','Planifiée', 'En pause')
        """,
        (id_campagne,),
    )
    return int(cur.rowcount or 0)


def _close_if_objective_reached(conn: sqlite3.Connection, id_campagne: str, objectif: str) -> int:
    """
    On ferme (Closed) toutes les lignes dont statut_actuel atteint l'objectif du modèle.
    Robustesse: comparaison normalisée via objective_reached (python rowid).
    """
    objectif = _norm_str(objectif)
    if not objectif:
        return 0

    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT rowid as __rid, statut_actuel, Action
        FROM {CLIENTS_CAMPAGNES_TABLE}
        WHERE ID_CAMPAGNE=?
          AND COALESCE(Etat_campagne,'') IN ('En cours','Planifiée', 'En pause')
          AND COALESCE(Action,'') <> 'Closed'
        """,
        (id_campagne,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    n = 0
    for r in rows:
        rid = int(r["__rid"])
        if objective_reached(r.get("statut_actuel"), objectif):
            cur.execute(
                f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET Action='Closed', Canal='Closed' WHERE rowid=?",
                (rid,),
            )
            n += int(cur.rowcount or 0)
    return n


def _cancel_if_rupture_relation(conn: sqlite3.Connection, id_campagne: str) -> int:
    cols = set(_clients_columns(conn))
    if "STATUT_CLIENT" not in cols and "statut_client" not in cols:
        return 0

    statut_col = "STATUT_CLIENT" if "STATUT_CLIENT" in cols else "statut_client"

    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE {CLIENTS_CAMPAGNES_TABLE}
        SET statut_actuel = 'canceled'
        WHERE ID_CAMPAGNE = ?
          AND COALESCE(Etat_campagne,'') IN ('En cours','Planifiée', 'En pause')
          AND EXISTS (
              SELECT 1
              FROM {CLIENTS_TABLE} cl
              WHERE cl.radical_compte = {CLIENTS_CAMPAGNES_TABLE}.Radical_compte
                AND LOWER(TRIM(COALESCE(cl."{statut_col}",''))) = LOWER('Rupture de relation')
          )
        """,
        (id_campagne,),
    )
    return int(cur.rowcount or 0)


def _update_campaigns_status_from_dates(campagnes: List[Dict[str, Any]]) -> Dict[str, int]:
    today = date.today()
    counts = {"to_en_cours": 0, "to_terminee": 0}

    for c in campagnes:
        id_c = _norm_str(c.get("id_campagne"))
        etat = _norm_str(c.get("etat") or c.get("etat_campagne"))
        d0 = _parse_iso_date(c.get("date_debut"))
        d1 = _parse_iso_date(c.get("date_fin"))

        if not id_c or etat == "Annulée" or not d0 or not d1:
            continue

        if etat == "En pause":
            continue

        if etat == "Planifiée" and d0 <= today <= d1:
            update_etat(id_c, "En cours")
            set_clients_etat_for_campagne(id_c, "En cours")
            counts["to_en_cours"] += 1

        if etat == "En cours" and d1 < today:
            update_etat(id_c, "Terminée")
            set_clients_etat_for_campagne(id_c, "Terminée")
            counts["to_terminee"] += 1

    return counts


def _recompute_nb_jour_last_action(conn: sqlite3.Connection) -> int:
    today_iso = date.today().isoformat()
    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE {CLIENTS_CAMPAGNES_TABLE}
        SET NB_jour_last_action = CASE
            WHEN COALESCE(Date_last_action,'') = '' THEN 0
            ELSE CAST((julianday(?) - julianday(substr(Date_last_action,1,10))) AS INTEGER)
        END
        WHERE COALESCE(Etat_campagne,'') IN ('En cours','Planifiée', 'En pause')
        """,
        (today_iso,),
    )
    return int(cur.rowcount or 0)


def _advance_en_attente_rows(conn: sqlite3.Connection, id_campagne: str, liste_action: List[Dict[str, Any]]) -> int:
    if not isinstance(liste_action, list) or len(liste_action) == 0:
        return 0

    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        f"""
        SELECT rowid as __rid, *
        FROM {CLIENTS_CAMPAGNES_TABLE}
        WHERE ID_CAMPAGNE = ?
          AND COALESCE(Etat_campagne,'') IN ('En cours','Planifiée', 'En pause')
          AND COALESCE(Action,'') = 'En attente'
        """,
        (id_campagne,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    changed = 0

    for r in rows:
        rid = int(r["__rid"])
        id_action = _norm_str(r.get("ID_Action"))
        current = find_bloc_by_id(liste_action, id_action)
        if not current:
            continue

        nxt = pick_next_child(liste_action, current, r)
        if not nxt:
            continue

        new_id = _norm_str(nxt.get("ID"))
        new_canal = _norm_str(nxt.get("Canal"))
        new_action = _norm_str(nxt.get("Action"))

        if not new_id or not new_action:
            continue

        cur.execute(
            f"""
            UPDATE {CLIENTS_CAMPAGNES_TABLE}
            SET ID_Action = ?, Canal = ?, Action = ?
            WHERE rowid = ?
            """,
            (new_id, new_canal, new_action, rid),
        )
        changed += int(cur.rowcount or 0)

    return int(changed)


def _rebuild_outputs_for_all_en_cours(conn: sqlite3.Connection, campagnes: List[Dict[str, Any]]) -> Dict[str, int]:
    ensure_crc_input_table()
    ensure_vers_da_table()
    ensure_vers_cc_table()

    clear_crc_input()
    cur = conn.cursor()
    cur.execute("DELETE FROM vers_da")
    cur.execute("DELETE FROM vers_cc")
    conn.commit()

    n_crc = 0
    n_da = 0
    n_cc = 0

    for c in campagnes:
        etat = _norm_str(c.get("etat") or c.get("etat_campagne"))
        if etat != "En cours":
            continue
        id_c = _norm_str(c.get("id_campagne"))
        if not id_c:
            continue

        n_crc += int(fill_crc_input_from_clients_campagnes(id_c) or 0)
        n_da += int(fill_action_vers_da_from_clients_campagnes(id_c) or 0)
        n_cc += int(fill_action_vers_cc_from_clients_campagnes(id_c) or 0)

    return {"crc_input": n_crc, "vers_da": n_da, "vers_cc": n_cc}


# =========================================================
# Public (lié au bouton refresh)
# =========================================================
def run_batch_manuel() -> Dict[str, Any]:
    """
    Ordre EXACT demandé + ajout:
    - close objectif (Closed)
    - traitement mails après MAJ/advance et avant rebuild outputs
    """
    ensure_clients_campagnes()

    campagnes = list_all_campagnes()
    actives = _list_active_campaigns(campagnes)

    out: Dict[str, Any] = {
        "statut_actuel_updated": 0,
        "rupture_canceled": 0,
        "campagnes_status": {"to_en_cours": 0, "to_terminee": 0},
        "nb_jour_last_action_updated": 0,
        "en_attente_advanced": 0,
        "closed_objectif": 0,
        "mails_processed": None,
        "outputs_rebuilt": {"crc_input": 0, "vers_da": 0, "vers_cc": 0},
    }

    conn = _connect()
    try:
        # 1) update statut_actuel from clients variable_cible (par campagne)
        for c in actives:
            id_c = _norm_str(c.get("id_campagne"))
            id_modele = _norm_str(c.get("id_modele"))
            if not id_c or not id_modele:
                continue

            variable_cible, objectif, _liste_action = _load_modele_meta(conn, id_modele)
            out["statut_actuel_updated"] += _update_statut_actuel_from_clients(conn, id_c, variable_cible)

            # 2) rupture relation -> canceled
            out["rupture_canceled"] += _cancel_if_rupture_relation(conn, id_c)

            # NEW: close objectif
            out["closed_objectif"] += _close_if_objective_reached(conn, id_c, objectif)

        conn.commit()

        # 3) update campagnes statuses
        out["campagnes_status"] = _update_campaigns_status_from_dates(campagnes)

        campagnes = list_all_campagnes()
        actives = _list_active_campaigns(campagnes)

        # 4) recompute NB_jour_last_action
        out["nb_jour_last_action_updated"] = _recompute_nb_jour_last_action(conn)
        conn.commit()

        # 5) advance En attente
        for c in actives:
            id_c = _norm_str(c.get("id_campagne"))
            id_modele = _norm_str(c.get("id_modele"))
            if not id_c or not id_modele:
                continue
            _var, objectif, liste_action = _load_modele_meta(conn, id_modele)

            # re-close objectif au cas où NB_jour ou update a modifié des conditions externes
            out["closed_objectif"] += _close_if_objective_reached(conn, id_c, objectif)

            out["en_attente_advanced"] += _advance_en_attente_rows(conn, id_c, liste_action)

        conn.commit()

        # NEW: 5bis) traiter mails (après mises à jour/advance)
        out["mails_processed"] = run_mail_meta_loop(max_passes=10, limit_rows_per_pass=5000)

        # 6) rebuild outputs
        out["outputs_rebuilt"] = _rebuild_outputs_for_all_en_cours(conn, campagnes)

    finally:
        conn.close()

    return out


if __name__ == "__main__":
    res = run_batch_manuel()
    print("[BATCH] OK:", res)
