from __future__ import annotations

import sqlite3
from typing import Any, Dict, List

from app.storage.db import DB_PATH

TABLE_NAME = "clients_campagnes"

# ✅ Schéma aligné avec campagne_service.py + crc_engine.py
CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    ID_CAMPAGNE           TEXT NOT NULL,
    Radical_compte        TEXT NOT NULL,

    statut_avant_campagne TEXT,
    statut_actuel         TEXT,

    Etat_campagne         TEXT,

    NB_jour_campagne      INTEGER DEFAULT 0,

    ID_Action             TEXT,
    Canal                 TEXT,
    Action                TEXT,

    Last_action           TEXT,
    Resultat_last_action  TEXT,
    Date_last_action      TEXT,

    NB_jour_last_action   INTEGER,

    NB_appel              INTEGER DEFAULT 0,
    NB_mail               INTEGER DEFAULT 0,
    NB_sms                INTEGER DEFAULT 0,
    NB_message            INTEGER DEFAULT 0,
    NB_approche_commercial INTEGER DEFAULT 0,

    PRIMARY KEY (ID_CAMPAGNE, Radical_compte)
)
"""


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def ensure_table() -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(CREATE_SQL)
    conn.commit()
    conn.close()


def _table_cols(cur: sqlite3.Cursor) -> List[str]:
    cur.execute(f"PRAGMA table_info({TABLE_NAME})")
    return [r[1] for r in cur.fetchall()]


def bulk_insert_clients(rows: List[Dict[str, Any]]) -> None:
    """
    ✅ Attendu par campagne_service.py
    rows = liste de dicts (colonnes -> valeurs)
    """
    if not rows:
        return

    ensure_table()
    conn = _connect()
    cur = conn.cursor()

    cols_in_table = set(_table_cols(cur))

    # normalise: ne garde que colonnes existantes
    clean_rows: List[Dict[str, Any]] = []
    for r in rows:
        rr = {k: r.get(k) for k in r.keys() if k in cols_in_table}
        clean_rows.append(rr)

    cols = sorted({k for r in clean_rows for k in r.keys()})
    if not cols:
        conn.close()
        return

    placeholders = ",".join(["?"] * len(cols))
    col_list = ",".join([f'"{c}"' for c in cols])

    # update on conflict (sauf PK)
    update_cols = [c for c in cols if c not in ("ID_CAMPAGNE", "Radical_compte")]
    update_sql = ", ".join([f'"{c}"=excluded."{c}"' for c in update_cols]) if update_cols else ""

    sql = f"""
    INSERT INTO {TABLE_NAME} ({col_list})
    VALUES ({placeholders})
    ON CONFLICT(ID_CAMPAGNE, Radical_compte)
    DO UPDATE SET {update_sql}
    """

    values = []
    for r in clean_rows:
        values.append(tuple(r.get(c) for c in cols))

    cur.executemany(sql, values)
    conn.commit()
    conn.close()


def set_clients_etat_for_campagne(id_campagne: str, new_etat: str) -> None:
    """
    ✅ Attendu par campagne_service.py
    """
    ensure_table()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        f'UPDATE {TABLE_NAME} SET Etat_campagne = ? WHERE ID_CAMPAGNE = ?',
        (new_etat, id_campagne),
    )
    conn.commit()
    conn.close()


def list_by_campagne(id_campagne: str) -> List[Dict[str, Any]]:
    ensure_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        f"SELECT * FROM {TABLE_NAME} WHERE ID_CAMPAGNE = ? ORDER BY Radical_compte",
        (id_campagne,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def list_all() -> List[Dict[str, Any]]:
    ensure_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {TABLE_NAME} ORDER BY ID_CAMPAGNE DESC, Radical_compte")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
