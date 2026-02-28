import os
import sqlite3

DB_PATH = os.getenv("MA_DB_PATH", "database.db")  # adapte si besoin

def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]  # r[1] = name
    return column in cols

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    table = "modeles"
    col = "ui_positions"

    if not column_exists(cur, table, col):
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
        conn.commit()
        print(f"✅ Colonne '{col}' ajoutée à '{table}'")
    else:
        print(f"ℹ️ Colonne '{col}' existe déjà dans '{table}'")

    conn.close()

if __name__ == "__main__":
    main()