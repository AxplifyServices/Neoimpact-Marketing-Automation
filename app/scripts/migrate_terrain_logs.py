from __future__ import annotations

import sqlite3
from pathlib import Path


# ⚠️ adapte si ton fichier sqlite est ailleurs
DB_PATH = Path("database.db")


def table_exists(cur: sqlite3.Cursor, table_name: str) -> bool:
    cur.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name=?
        """,
        (table_name,),
    )
    return cur.fetchone() is not None


def ensure_terrain_logs_table(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS terrain_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_campagne TEXT,
            radical_compte TEXT,
            queue TEXT,
            action TEXT,
            resultat TEXT,
            source TEXT,
            date_event TEXT
        )
        """
    )
    print("✅ Table terrain_logs prête")


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Base SQLite introuvable: {DB_PATH.resolve()}")

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    try:
        ensure_terrain_logs_table(cur)

        conn.commit()
        print("🎉 Migration terrain_logs terminée avec succès")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()