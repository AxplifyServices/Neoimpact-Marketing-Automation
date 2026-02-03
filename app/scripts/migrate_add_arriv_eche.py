from __future__ import annotations

import sqlite3
from app.storage.db import DB_PATH

TABLE = "clients_campagnes"
COL = "arriv_eche"

def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({TABLE})")
        cols = {r[1] for r in cur.fetchall()}

        if COL not in cols:
            cur.execute(f"ALTER TABLE {TABLE} ADD COLUMN {COL} TEXT")
            print(f"[MIGRATION] Colonne ajoutée: {TABLE}.{COL}")
        else:
            print(f"[MIGRATION] Colonne déjà présente: {TABLE}.{COL}")

        cur.execute(f"UPDATE {TABLE} SET {COL}='Non' WHERE {COL} IS NULL OR TRIM({COL})=''")
        print("[MIGRATION] Valeurs initialisées à 'Non' (NULL/vides)")

        conn.commit()
        print("[MIGRATION] OK")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
