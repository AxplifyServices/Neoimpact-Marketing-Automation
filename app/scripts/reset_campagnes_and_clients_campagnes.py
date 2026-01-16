from __future__ import annotations

import sqlite3
from app.storage.db import DB_PATH


TABLES_TO_CLEAR = [
    "clients_campagnes",
    "campagnes",
]


def table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cur.fetchone() is not None


def clear_table(cur: sqlite3.Cursor, table: str) -> int:
    cur.execute(f"DELETE FROM {table}")
    return cur.rowcount


def main() -> None:
    print("=== RESET CAMPAGNES ===")
    print(f"DB_PATH = {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()

        total_deleted = {}

        for table in TABLES_TO_CLEAR:
            if not table_exists(cur, table):
                print(f"[SKIP] Table absente : {table}")
                continue

            deleted = clear_table(cur, table)
            total_deleted[table] = deleted
            print(f"[OK] {table} : {deleted} lignes supprimées")

        conn.commit()

        print("\n=== RÉSUMÉ ===")
        for table, count in total_deleted.items():
            print(f"{table}: {count} lignes supprimées")

        print("\nRESET TERMINÉ ✅")

    except Exception as e:
        conn.rollback()
        print("❌ ERREUR — rollback effectué")
        raise e

    finally:
        conn.close()


if __name__ == "__main__":
    main()
