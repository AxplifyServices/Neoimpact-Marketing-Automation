import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "database.db")

def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name});")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def add_conversion_column():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    table_name = "clients_campagnes"
    column_name = "conversion"

    if column_exists(cur, table_name, column_name):
        print(f"✅ La colonne '{column_name}' existe déjà.")
    else:
        print(f"➕ Ajout de la colonne '{column_name}'...")
        cur.execute(f"""
            ALTER TABLE {table_name}
            ADD COLUMN conversion INTEGER DEFAULT 0
        """)
        conn.commit()
        print("✅ Colonne ajoutée avec succès.")

    conn.close()


if __name__ == "__main__":
    add_conversion_column()
