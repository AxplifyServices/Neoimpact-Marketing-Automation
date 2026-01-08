from __future__ import annotations

import os
import sqlite3
from datetime import date
from typing import Any, Dict, List, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "clients.db")

TABLE_NAME = "campagnes"

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id_campagne   TEXT PRIMARY KEY,
    nom_campagne  TEXT NOT NULL,
    id_modele     TEXT NOT NULL,
    id_cible      TEXT NOT NULL,
    date_creation TEXT,
    date_debut    TEXT,
    date_fin      TEXT,
    etat_campagne TEXT
);
"""

EXPECTED_COLS = [
    "id_campagne",
    "nom_campagne",
    "id_modele",
    "id_cible",
    "date_creation",
    "date_debut",
    "date_fin",
    "etat_campagne",
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
            cur.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {c} TEXT")

    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_etat ON {TABLE_NAME}(etat_campagne)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_modele ON {TABLE_NAME}(id_modele)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_cible ON {TABLE_NAME}(id_cible)")

    conn.commit()
    conn.close()


def _new_id(cur: sqlite3.Cursor) -> str:
    cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
    n = cur.fetchone()[0] or 0
    return f"CA{n+1:06d}"


def insert_campagne(
    nom_campagne: str,
    id_modele: str,
    id_cible: str,
    date_debut: str,
    date_fin: str,
    etat_campagne: str,
) -> str:
    ensure_table()
    conn = _connect()
    cur = conn.cursor()

    id_campagne = _new_id(cur)
    dc = date.today().isoformat()

    cur.execute(
        f"""
        INSERT INTO {TABLE_NAME}
        (id_campagne, nom_campagne, id_modele, id_cible, date_creation, date_debut, date_fin, etat_campagne)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (id_campagne, nom_campagne, id_modele, id_cible, dc, date_debut, date_fin, etat_campagne),
    )

    conn.commit()
    conn.close()
    return id_campagne


def update_etat(id_campagne: str, new_etat: str) -> None:
    ensure_table()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE {TABLE_NAME} SET etat_campagne = ? WHERE id_campagne = ?",
        (new_etat, id_campagne),
    )
    conn.commit()
    conn.close()


def get_campagne(id_campagne: str) -> Optional[Dict[str, Any]]:
    ensure_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {TABLE_NAME} WHERE id_campagne = ?", (id_campagne,))
    r = cur.fetchone()
    conn.close()
    return dict(r) if r else None


def list_campagnes_active() -> List[Dict[str, Any]]:
    """Uniquement En cours + Planifiée (PAS Annulée)."""
    ensure_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT *
        FROM {TABLE_NAME}
        WHERE etat_campagne IN ('En cours', 'Planifiée')
        ORDER BY date_creation DESC, id_campagne DESC
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def list_all_campagnes() -> List[Dict[str, Any]]:
    ensure_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {TABLE_NAME} ORDER BY date_creation DESC, id_campagne DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
