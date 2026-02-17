# scripts/recreate_clients_campagnes.py
import os
import sqlite3

def get_db_path() -> str:
    # Priorité: variable d'env, sinon fallback
    # (tu peux remplacer le fallback par ton chemin exact)
    return os.getenv("DB_PATH", "database.db")

def main():
    db_path = get_db_path()
    print(f"[INFO] DB_PATH = {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        # 1) drop sans backup
        print("[INFO] DROP TABLE clients_campagnes ...")
        cur.execute("DROP TABLE IF EXISTS clients_campagnes")

        # 2) recreate sans les 2 colonnes statut_*
        print("[INFO] CREATE TABLE clients_campagnes (new schema) ...")
        cur.execute("""
        CREATE TABLE clients_campagnes (
            Nom_campagne            TEXT,
            ID_CAMPAGNE             TEXT,
            Radical_compte          TEXT,
            Etat_campagne           TEXT,
            NB_jour_campagne        INTEGER,
            ID_Action               TEXT,
            Canal                   TEXT,
            Action                  TEXT,
            Last_action             TEXT,
            Resultat_last_action    TEXT,
            Date_last_action        TEXT,
            NB_jour_last_action     INTEGER,
            NB_appel                INTEGER,
            NB_mail                 INTEGER,
            NB_sms                  INTEGER,
            NB_message              INTEGER,
            NB_approche_commercial  INTEGER,
            arriv_eche              TEXT DEFAULT 'Non',
            date_debut_campagne     TEXT,
            nb_jour_debut_campagne  INTEGER
        )
        """)

        # 3) index (optionnel mais recommandé)
        print("[INFO] Create indexes ...")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cc_idcamp ON clients_campagnes(ID_CAMPAGNE)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cc_radical ON clients_campagnes(Radical_compte)")

        conn.commit()

        # 4) Vérif immédiate
        cur.execute("PRAGMA table_info(clients_campagnes)")
        cols = [r[1] for r in cur.fetchall()]
        print("[OK] Colonnes =", cols)

        if "statut_avant_campagne" in cols or "statut_actuel" in cols:
            raise RuntimeError("ERREUR: les colonnes statut_* existent encore")

        print("[SUCCESS] Table clients_campagnes recréée sans statut_*.")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
