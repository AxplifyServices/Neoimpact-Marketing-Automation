# reset_tables_historiques.py
# Usage:
#   python reset_tables_historiques.py "C:\chemin\vers\database.db"
# Ou sans argument -> cherche "database.db" dans le dossier courant

import os
import sys
import shutil
import sqlite3
from datetime import datetime

TABLES_TO_DROP = [
    "crc_input",
    "action_vers_cc",
    "action_vers_da",
    "traitement_mail",
    "vers_cc",   # demandé : supprimer
    "vers_da",   # demandé : supprimer
]

DDL = {
    # colonnes du screen
    "crc_input": """
    CREATE TABLE IF NOT EXISTS crc_input (
        id_campagne     TEXT NOT NULL,
        radical_compte  TEXT NOT NULL,
        date_affectation TEXT,
        nb_jour_affecte INTEGER,
        nom             TEXT,
        prenom          TEXT,
        numero_tel      TEXT,
        region          TEXT,
        agence          TEXT,
        gestionnaire    TEXT,
        colonne         TEXT,
        objectif        TEXT,
        statut_actuel   TEXT,
        PRIMARY KEY (id_campagne, radical_compte)
    );
    """,

    "action_vers_cc": """
    CREATE TABLE IF NOT EXISTS action_vers_cc (
        id_campagne     TEXT NOT NULL,
        radical_compte  TEXT NOT NULL,
        date_affectation TEXT,
        nb_jour_affecte INTEGER,
        nom             TEXT,
        prenom          TEXT,
        numero_tel      TEXT,
        region          TEXT,
        agence          TEXT,
        gestionnaire    TEXT,
        colonne         TEXT,
        objectif        TEXT,
        statut_actuel   TEXT,
        PRIMARY KEY (id_campagne, radical_compte)
    );
    """,

    "action_vers_da": """
    CREATE TABLE IF NOT EXISTS action_vers_da (
        id_campagne     TEXT NOT NULL,
        radical_compte  TEXT NOT NULL,
        date_affectation TEXT,
        nb_jour_affecte INTEGER,
        nom             TEXT,
        prenom          TEXT,
        numero_tel      TEXT,
        region          TEXT,
        agence          TEXT,
        gestionnaire    TEXT,
        colonne         TEXT,
        objectif        TEXT,
        statut_actuel   TEXT,
        PRIMARY KEY (id_campagne, radical_compte)
    );
    """,

    # colonnes du screen
    "traitement_mail": """
    CREATE TABLE IF NOT EXISTS traitement_mail (
        id_campagne     TEXT NOT NULL,
        radical_compte  TEXT NOT NULL,
        nom             TEXT,
        prenom          TEXT,
        mail            TEXT,
        colonne         TEXT,
        objectif        TEXT,
        statut_actuel   TEXT,
        PRIMARY KEY (id_campagne, radical_compte)
    );
    """,
}

def backup_db(db_path: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(
        os.path.dirname(db_path),
        f"database_backup_{ts}.db"
    )
    shutil.copy2(db_path, backup_path)
    return backup_path

def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?;",
        (table_name,)
    )
    return cur.fetchone() is not None

def show_table_columns(conn: sqlite3.Connection, table_name: str) -> None:
    cur = conn.execute(f"PRAGMA table_info({table_name});")
    rows = cur.fetchall()
    print(f"\n== {table_name} ==")
    for r in rows:
        # r = (cid, name, type, notnull, dflt_value, pk)
        print(f"- {r[1]} ({r[2]}) pk={r[5]} notnull={r[3]}")

def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "database.db"
    db_path = os.path.abspath(db_path)

    if not os.path.isfile(db_path):
        print(f"[ERREUR] DB introuvable: {db_path}")
        print("=> Passe le chemin en argument, ex:")
        print(r'   python reset_tables_historiques.py "C:\...\database.db"')
        sys.exit(1)

    backup_path = backup_db(db_path)
    print(f"[OK] Backup créé: {backup_path}")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = OFF;")  # pour éviter blocages si FK
        conn.execute("BEGIN;")

        # 1) DROP tables demandées
        for t in TABLES_TO_DROP:
            if table_exists(conn, t):
                conn.execute(f"DROP TABLE IF EXISTS {t};")
                print(f"[DROP] {t}")
            else:
                print(f"[SKIP] {t} (n'existe pas)")

        # 2) Recreate tables (sans vers_cc / vers_da)
        for t, ddl in DDL.items():
            conn.execute(ddl)
            print(f"[CREATE] {t}")

        conn.execute("COMMIT;")
        print("[OK] Commit terminé.")

        # 3) Vérification structure
        for t in DDL.keys():
            show_table_columns(conn, t)

    except Exception as e:
        conn.execute("ROLLBACK;")
        print("[ERREUR] Rollback effectué.")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
