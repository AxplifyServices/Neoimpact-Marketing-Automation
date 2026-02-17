from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Iterable, Tuple

from app.storage.db import DB_PATH

TABLE = "clients_cibles"
CIBLES_TABLE = "cibles"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    return conn


def ensure_table() -> None:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                ID_CIBLE         TEXT NOT NULL,
                Radical_compte   TEXT NOT NULL,
                created_at       TEXT
            )
            """
        )
        # index + anti-doublon
        cur.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{TABLE} ON {TABLE}(ID_CIBLE, Radical_compte)")
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_cible ON {TABLE}(ID_CIBLE)")
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_rad ON {TABLE}(Radical_compte)")
        conn.commit()
    finally:
        conn.close()


def insert_only_members(id_cible: str, radicals: Iterable[str]) -> int:
    """
    Insert-only : ajoute les nouveaux (ID_CIBLE, Radical_compte).
    Ne supprime jamais.
    """
    ensure_table()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = [(id_cible, rc, now) for rc in radicals if str(rc).strip()]
    if not data:
        return 0

    conn = _connect()
    try:
        cur = conn.cursor()
        # SQLite >= 3.24: UPSERT; sinon remplace par INSERT OR IGNORE (ok car index unique)
        cur.executemany(
            f"""
            INSERT OR IGNORE INTO {TABLE}(ID_CIBLE, Radical_compte, created_at)
            VALUES (?, ?, ?)
            """,
            data,
        )
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        conn.close()


def get_volume(id_cible: str) -> int:
    ensure_table()
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE ID_CIBLE = ?", (id_cible,))
        return int(cur.fetchone()[0] or 0)
    finally:
        conn.close()


def update_cible_volume_if_column_exists(id_cible: str) -> None:
    """
    Met à jour cibles.volume si la colonne existe. Sinon no-op (pour éviter de casser).
    """
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({CIBLES_TABLE})")
        cols = {r[1] for r in cur.fetchall()}
        if "volume" not in cols and "Volume" not in cols:
            return

        col = "volume" if "volume" in cols else "Volume"
        vol = get_volume(id_cible)

        cur.execute(f'UPDATE {CIBLES_TABLE} SET "{col}" = ? WHERE id_cible = ? OR ID_CIBLE = ?', (vol, id_cible, id_cible))
        conn.commit()
    finally:
        conn.close()
