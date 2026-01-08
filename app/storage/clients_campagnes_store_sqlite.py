from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "clients.db")

TABLE_NAME = "clients_campagnes"

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    ID_CAMPAGNE           TEXT NOT NULL,
    Radical_compte        TEXT NOT NULL,

    statut_avant_campagne TEXT,
    statut_actuel         TEXT,

    Etat_campagne         TEXT,
    NB_jour_campagne      INTEGER,

    ID_Action             TEXT,
    Action                TEXT,

    Last_action           TEXT,
    Resultat_last_action  TEXT,
    Date_last_action      TEXT,
    NB_jour_last_action   INTEGER,

    NB_appel              INTEGER,
    NB_sms                INTEGER,
    NB_mail               INTEGER,
    NB_message            INTEGER,

    PRIMARY KEY (ID_CAMPAGNE, Radical_compte)
);
"""

EXPECTED_COLS = [
    "ID_CAMPAGNE", "Radical_compte",
    "statut_avant_campagne", "statut_actuel",
    "Etat_campagne", "NB_jour_campagne",
    "ID_Action", "Action",
    "Last_action", "Resultat_last_action", "Date_last_action", "NB_jour_last_action",
    "NB_appel", "NB_sms", "NB_mail", "NB_message",
]


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _table_cols(cur: sqlite3.Cursor, table: str) -> List[str]:
    cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def ensure_table() -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(CREATE_SQL)

    cols = set(_table_cols(cur, TABLE_NAME))
    for c in EXPECTED_COLS:
        if c not in cols:
            if c.startswith("NB_"):
                cur.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {c} INTEGER")
            else:
                cur.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {c} TEXT")

    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_camp ON {TABLE_NAME}(ID_CAMPAGNE)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_etat ON {TABLE_NAME}(Etat_campagne)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_rc ON {TABLE_NAME}(Radical_compte)")

    conn.commit()
    conn.close()


def bulk_insert_clients(rows: List[Dict[str, Any]]) -> int:
    ensure_table()
    conn = _connect()
    cur = conn.cursor()

    sql = f"""
    INSERT INTO {TABLE_NAME} (
        ID_CAMPAGNE, Radical_compte,
        statut_avant_campagne, statut_actuel,
        Etat_campagne, NB_jour_campagne,
        ID_Action, Action,
        Last_action, Resultat_last_action, Date_last_action, NB_jour_last_action,
        NB_appel, NB_sms, NB_mail, NB_message
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(ID_CAMPAGNE, Radical_compte) DO UPDATE SET
        statut_avant_campagne=excluded.statut_avant_campagne,
        statut_actuel=excluded.statut_actuel,
        Etat_campagne=excluded.Etat_campagne,
        NB_jour_campagne=excluded.NB_jour_campagne,
        ID_Action=excluded.ID_Action,
        Action=excluded.Action
    """

    for r in rows:
        cur.execute(
            sql,
            (
                r.get("ID_CAMPAGNE"),
                r.get("Radical_compte"),
                r.get("statut_avant_campagne"),
                r.get("statut_actuel"),
                r.get("Etat_campagne"),
                r.get("NB_jour_campagne"),
                r.get("ID_Action"),
                r.get("Action"),
                r.get("Last_action"),
                r.get("Resultat_last_action"),
                r.get("Date_last_action"),
                r.get("NB_jour_last_action"),
                r.get("NB_appel"),
                r.get("NB_sms"),
                r.get("NB_mail"),
                r.get("NB_message"),
            ),
        )

    conn.commit()
    conn.close()
    return len(rows)


def list_by_campagne(id_campagne: str) -> List[Dict[str, Any]]:
    ensure_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {TABLE_NAME} WHERE ID_CAMPAGNE = ? ORDER BY Radical_compte", (id_campagne,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def set_clients_etat_for_campagne(id_campagne: str, new_etat: str) -> None:
    """Quand une campagne est annulée -> on met aussi Etat_campagne côté client."""
    ensure_table()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(f"UPDATE {TABLE_NAME} SET Etat_campagne = ? WHERE ID_CAMPAGNE = ?", (new_etat, id_campagne))
    conn.commit()
    conn.close()


def list_all() -> List[Dict[str, Any]]:
    ensure_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {TABLE_NAME} ORDER BY ID_CAMPAGNE DESC, Radical_compte")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
