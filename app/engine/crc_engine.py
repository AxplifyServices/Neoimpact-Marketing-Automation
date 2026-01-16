from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

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


# =========================================================
# Queue helpers (utilisés par DA/CC)
# =========================================================
def get_next_row_from_queue(table: str) -> Optional[Dict[str, Any]]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if not _table_exists(cur, table):
        conn.close()
        return None

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
# CRC-specific wrappers (utilisés par CRC_int.py)
# =========================================================
def get_next_crc_input_row() -> Optional[Dict[str, Any]]:
    return get_next_row_from_queue(CRC_INPUT_TABLE)


def skip_current_row(id_campagne: str, radical_compte: str) -> None:
    delete_row_from_queue(CRC_INPUT_TABLE, id_campagne, radical_compte)


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
        # adapte l'URL si nécessaire
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
