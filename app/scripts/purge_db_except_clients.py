# app/scripts/purge_db_except_clients.py

import sqlite3
from app.storage.db import DB_PATH


EXCLUDED_TABLES = {"clients"}  # tables à ne PAS vider


def purge_database_except_clients():
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()

        # Récupérer toutes les tables utilisateur
        cur.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
        """)
        tables = [row[0] for row in cur.fetchall()]

        # Filtrer celles à purger
        tables_to_purge = [
            t for t in tables
            if t not in EXCLUDED_TABLES
        ]

        print("Tables trouvées :", tables)
        print("Tables à purger :", tables_to_purge)

        # Transaction
        cur.execute("BEGIN")

        for table in tables_to_purge:
            print(f"🧹 Purge table: {table}")
            cur.execute(f'DELETE FROM "{table}"')

        # Reset autoincrement si sqlite_sequence existe
        cur.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='sqlite_sequence'
        """)
        if cur.fetchone():
            print("🔁 Reset des séquences AUTOINCREMENT")
            cur.execute("DELETE FROM sqlite_sequence")

        conn.commit()
        print("✅ Purge terminée avec succès.")

    except Exception as e:
        conn.rollback()
        print("❌ Erreur durant la purge:", e)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    purge_database_except_clients()
