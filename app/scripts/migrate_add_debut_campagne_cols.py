# scripts/migrate_add_debut_campagne_cols.py
import sqlite3

DB_PATH = "database.db"  # <-- adapte si besoin

TABLE = "clients_campagnes"

def col_exists(cur, table, col):
    cur.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in cur.fetchall())

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Ajout colonnes si absentes
    if not col_exists(cur, TABLE, "date_debut_campagne"):
        cur.execute(f"ALTER TABLE {TABLE} ADD COLUMN date_debut_campagne TEXT")
        print("✅ Added date_debut_campagne")

    if not col_exists(cur, TABLE, "nb_jour_debut_campagne"):
        cur.execute(f"ALTER TABLE {TABLE} ADD COLUMN nb_jour_debut_campagne INTEGER")
        print("✅ Added nb_jour_debut_campagne")

    conn.commit()
    conn.close()
    print("✅ Migration done")

if __name__ == "__main__":
    main()
