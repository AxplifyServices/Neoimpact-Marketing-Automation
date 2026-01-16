from __future__ import annotations

import sqlite3

from app.storage.db import DB_PATH


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    return column in cols


def main() -> None:
    table = "clients_campagnes"
    col = "NB_approche_commercial"

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()

        # Vérifier table
        cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        )
        if cur.fetchone() is None:
            raise RuntimeError(
                f"Table '{table}' introuvable dans la DB: {DB_PATH}. "
                "Assure-toi d'avoir bien créé database.db (refonte_db.py) et que DB_PATH pointe dessus."
            )

        # Si colonne déjà là -> rien à faire
        if _column_exists(conn, table, col):
            print(f"[SKIP] Colonne déjà existante: {table}.{col}")
            return

        # Ajouter colonne (DEFAULT 0)
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} INTEGER DEFAULT 0")
        conn.commit()

        # Sécuriser les NULL éventuels
        cur.execute(f"UPDATE {table} SET {col} = 0 WHERE {col} IS NULL")
        conn.commit()

        print(f"[OK] Colonne ajoutée: {table}.{col} (INTEGER DEFAULT 0)")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
