from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional, List, Tuple

import sqlite3
import requests

from app.storage.db import DB_PATH
from app.engine.contact_client_engine import apply_result_from_queue


CRC_INPUT_TABLE = "crc_input"


# =========================================================
# DB helpers
# =========================================================
def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def _today_iso() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# =========================================================
# ✅ NEW: Campaign listing (CRC / DA / CC)
# =========================================================
def list_campaigns_in_queue(queue_table: str) -> List[Tuple[str, str]]:
    """
    Retourne [(ID_CAMPAGNE, nom_campagne)] présents dans une queue donnée (vers_da / vers_cc / crc_input si besoin).
    """
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if not _table_exists(cur, queue_table):
        conn.close()
        return []

    cur.execute(
        f"""
        SELECT DISTINCT
            q.ID_CAMPAGNE AS id_campagne,
            c.nom_campagne AS nom_campagne
        FROM {queue_table} q
        LEFT JOIN campagnes c ON c.id_campagne = q.ID_CAMPAGNE
        WHERE q.ID_CAMPAGNE IS NOT NULL AND TRIM(q.ID_CAMPAGNE) <> ''
        ORDER BY COALESCE(c.nom_campagne, q.ID_CAMPAGNE) ASC
        """
    )
    rows = cur.fetchall()
    conn.close()

    out: List[Tuple[str, str]] = []
    for r in rows:
        cid = (r["id_campagne"] or "").strip()
        if not cid:
            continue
        cname = (r["nom_campagne"] or "").strip()
        out.append((cid, cname))
    return out


def list_campaigns_in_crc_queue() -> List[Tuple[str, str]]:
    return list_campaigns_in_queue(CRC_INPUT_TABLE)


# =========================================================
# Queue helpers (utilisés par DA/CC)
# =========================================================
def get_next_row_from_queue(table: str, id_campagne_filter: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Ancien comportement si id_campagne_filter est None.
    Sinon: retourne la prochaine ligne de la queue pour cette campagne.
    """
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if not _table_exists(cur, table):
        conn.close()
        return None

    if id_campagne_filter:
        cur.execute(
            f"""
            SELECT * FROM {table}
            WHERE TRIM(ID_CAMPAGNE) = ?
            ORDER BY date_creation_campagne ASC, COALESCE(date_last_action, '9999-12-31') ASC
            LIMIT 1
            """,
            (str(id_campagne_filter).strip(),),
        )
    else:
        cur.execute(
            f"""
            SELECT * FROM {table}
            ORDER BY date_creation_campagne ASC, COALESCE(date_last_action, '9999-12-31') ASC
            LIMIT 1
            """
        )

    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_row_from_queue(table: str, id_campagne: str, radical_compte: str) -> None:
    conn = _connect()
    cur = conn.cursor()

    if not _table_exists(cur, table):
        conn.close()
        return

    cur.execute(f"DELETE FROM {table} WHERE ID_CAMPAGNE = ? AND Radical_compte = ?", (id_campagne, radical_compte))
    conn.commit()
    conn.close()


# =========================================================
# ✅ NEW: navigation circulaire (Skip/Reculer) + flag échéance
# =========================================================
def get_ordered_rows_from_queue(table: str, id_campagne_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retourne la liste ordonnée des lignes d'une queue (utilisé par l'UI pour Skip/Reculer circulaire)."""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if not _table_exists(cur, table):
        conn.close()
        return []

    if id_campagne_filter:
        cur.execute(
            f"""
            SELECT * FROM {table}
            WHERE TRIM(ID_CAMPAGNE) = ?
            ORDER BY date_creation_campagne ASC, COALESCE(date_last_action, '9999-12-31') ASC
            """,
            (str(id_campagne_filter).strip(),),
        )
    else:
        cur.execute(
            f"""
            SELECT * FROM {table}
            ORDER BY date_creation_campagne ASC, COALESCE(date_last_action, '9999-12-31') ASC
            """
        )

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def move_row_to_end_of_queue(table: str, id_campagne: str, radical_compte: str) -> None:
    """Skip = on garde la ligne mais on la pousse à la fin (en mettant date_last_action à maintenant)."""
    conn = _connect()
    cur = conn.cursor()

    if not _table_exists(cur, table):
        conn.close()
        return

    cur.execute(
        f"""
        UPDATE {table}
        SET date_last_action = ?
        WHERE ID_CAMPAGNE = ? AND Radical_compte = ?
        """,
        (_now_iso(), str(id_campagne).strip(), str(radical_compte).strip()),
    )
    conn.commit()
    conn.close()


def get_arrive_eche_flag(id_campagne: str, radical_compte: str) -> bool:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT arriv_eche
            FROM clients_campagnes
            WHERE TRIM(ID_CAMPAGNE) = ? AND TRIM(Radical_compte) = ?
            LIMIT 1
            """,
            (str(id_campagne).strip(), str(radical_compte).strip()),
        )
        row = cur.fetchone()
        return bool(row and str(row["arriv_eche"]).strip() == "Oui")
    finally:
        conn.close()



# =========================================================
# CRC-specific wrappers (utilisés par CRC_int.py)
# =========================================================
def get_next_crc_input_row(id_campagne_filter: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return get_next_row_from_queue(CRC_INPUT_TABLE, id_campagne_filter=id_campagne_filter)


def skip_current_row(id_campagne: str, radical_compte: str) -> None:
    move_row_to_end_of_queue(CRC_INPUT_TABLE, id_campagne, radical_compte)


# =========================================================
# ✅ NEW: unifier traitement résultats (CRC + DA + CC)
# =========================================================
def apply_result_and_update_client_campagnes(row: Dict[str, Any], resultat_label: str) -> Dict[str, Any]:
    """
    Utilisé par CRC_int.py
    - applique le résultat sur clients_campagnes
    - supprime la ligne de crc_input
    - route vers crc/da/cc/mail selon nouvelle action
    """
    return apply_result_from_queue(row, resultat_label, CRC_INPUT_TABLE)


def apply_result_and_update_client_campagnes_from_queue(
    row: Dict[str, Any],
    resultat_label: str,
    queue_table: str,
) -> Dict[str, Any]:
    """
    Utilisé par DA_int.py / CC_int.py
    """
    return apply_result_from_queue(row, resultat_label, queue_table)


# =========================================================
# Téléphonie / API (inchangé)
# =========================================================
def call_client_api(numero_tel: str) -> Dict[str, Any]:
    """
    Appelle l'API (si tu en as une) - inchangé.
    """
    try:
        url = "http://127.0.0.1:8000/call"
        r = requests.post(url, json={"numero": numero_tel}, timeout=10)
        return {"ok": True, "status": r.status_code, "data": r.json() if r.content else {}}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def call_current_client(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Utilisé par CRC_int.py (bouton "Appeler") - inchangé.
    """
    numero = (row.get("Numero_Tel") or row.get("numero_tel") or "").strip()
    if not numero:
        return {"ok": False, "error": "Numero_Tel manquant"}
    return call_client_api(numero)

def prioritize_echeance_in_queue(queue_table: str, id_campagne_filter: Optional[str] = None) -> int:
    """
    Met les clients arrivant à échéance (clients_campagnes.arriv_eche='Oui') en tête de la queue,
    en forçant queue.date_last_action à '0000-01-01 00:00:00' pour ces lignes.

    - Safe: UPDATE uniquement (pas de DELETE/INSERT).
    - Compatible avec l'ordre actuel de lecture:
        ORDER BY date_creation_campagne ASC, COALESCE(date_last_action,'9999-12-31') ASC
      utilisé par get_next_row_from_queue / get_ordered_rows_from_queue.
    """
    conn = _connect()
    cur = conn.cursor()

    # table queue existe ?
    if not _table_exists(cur, queue_table):
        conn.close()
        return 0

    # Appliquer la priorisation (par campagne si filter fourni)
    if id_campagne_filter:
        cur.execute(
            f"""
            UPDATE {queue_table}
            SET date_last_action = '0000-01-01 00:00:00'
            WHERE TRIM(ID_CAMPAGNE) = ?
              AND (ID_CAMPAGNE, Radical_compte) IN (
                  SELECT TRIM(ID_CAMPAGNE), TRIM(Radical_compte)
                  FROM clients_campagnes
                  WHERE TRIM(ID_CAMPAGNE) = ?
                    AND TRIM(COALESCE(arriv_eche,'')) = 'Oui'
              )
            """,
            (str(id_campagne_filter).strip(), str(id_campagne_filter).strip()),
        )
    else:
        cur.execute(
            f"""
            UPDATE {queue_table}
            SET date_last_action = '0000-01-01 00:00:00'
            WHERE (ID_CAMPAGNE, Radical_compte) IN (
                SELECT TRIM(ID_CAMPAGNE), TRIM(Radical_compte)
                FROM clients_campagnes
                WHERE TRIM(COALESCE(arriv_eche,'')) = 'Oui'
            )
            """
        )

    conn.commit()
    n = cur.rowcount if cur.rowcount is not None else 0
    conn.close()
    return int(n)

# app/engine/crc_engine.py

def list_gestionnaires_in_queue(queue_table: str, id_campagne_filter: Optional[str] = None) -> List[str]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if not _table_exists(cur, queue_table):
        conn.close()
        return []

    where = []
    params: List[Any] = []
    if id_campagne_filter:
        where.append("TRIM(q.ID_CAMPAGNE) = ?")
        params.append(str(id_campagne_filter).strip())

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    cur.execute(
        f"""
        SELECT DISTINCT COALESCE(cl.Gestionnaire, '') AS gestionnaire
        FROM {queue_table} q
        LEFT JOIN clients cl ON cl.radical_compte = q.Radical_compte
        {where_sql}
        ORDER BY gestionnaire ASC
        """,
        params,
    )
    rows = cur.fetchall()
    conn.close()
    return [str(r["gestionnaire"]).strip() for r in rows if str(r["gestionnaire"]).strip()]


def get_queue_counts_by_gestionnaire(queue_table: str, id_campagne_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if not _table_exists(cur, queue_table):
        conn.close()
        return []

    where = []
    params: List[Any] = []
    if id_campagne_filter:
        where.append("TRIM(q.ID_CAMPAGNE) = ?")
        params.append(str(id_campagne_filter).strip())

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    cur.execute(
        f"""
        SELECT COALESCE(cl.Gestionnaire, '') AS gestionnaire, COUNT(*) AS nb
        FROM {queue_table} q
        LEFT JOIN clients cl ON cl.radical_compte = q.Radical_compte
        {where_sql}
        GROUP BY gestionnaire
        ORDER BY nb DESC, gestionnaire ASC
        """,
        params,
    )
    rows = cur.fetchall()
    conn.close()
    return [{"gestionnaire": r["gestionnaire"], "nb": int(r["nb"])} for r in rows]


def get_ordered_rows_from_queue(
    table: str,
    id_campagne_filter: Optional[str] = None,
    gestionnaire_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if not _table_exists(cur, table):
        conn.close()
        return []

    if gestionnaire_filter:
        where = ["TRIM(COALESCE(cl.Gestionnaire,'')) = ?"]
        params: List[Any] = [str(gestionnaire_filter).strip()]
        if id_campagne_filter:
            where.append("TRIM(q.ID_CAMPAGNE) = ?")
            params.append(str(id_campagne_filter).strip())

        where_sql = " AND ".join(where)
        cur.execute(
            f"""
            SELECT q.*
            FROM {table} q
            LEFT JOIN clients cl ON cl.radical_compte = q.Radical_compte
            WHERE {where_sql}
            ORDER BY q.date_creation_campagne ASC, COALESCE(q.date_last_action, '9999-12-31') ASC
            """,
            params,
        )
    else:
        # fallback identique à l'existant
        if id_campagne_filter:
            cur.execute(
                f"""
                SELECT * FROM {table}
                WHERE TRIM(ID_CAMPAGNE) = ?
                ORDER BY date_creation_campagne ASC, COALESCE(date_last_action, '9999-12-31') ASC
                """,
                (str(id_campagne_filter).strip(),),
            )
        else:
            cur.execute(
                f"""
                SELECT * FROM {table}
                ORDER BY date_creation_campagne ASC, COALESCE(date_last_action, '9999-12-31') ASC
                """
            )

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

