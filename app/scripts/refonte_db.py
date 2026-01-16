# app/scripts/refonte_db.py
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import List


# =========================================================
# PATHS
# =========================================================
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

OLD_DB = os.path.join(PROJECT_ROOT, "clients.db")     # ancienne base
NEW_DB = os.path.join(PROJECT_ROOT, "database.db")    # nouvelle base


# =========================================================
# HELPERS
# =========================================================
def _connect(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def _table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    )
    return cur.fetchone() is not None


def _get_create_table_sql(conn: sqlite3.Connection, table: str) -> str:
    cur = conn.cursor()
    cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        raise RuntimeError(f"Impossible de récupérer le SQL de création de la table: {table}")
    return str(row[0])


def _get_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def _copy_table_schema_and_data(old_conn, new_conn, table: str) -> int:
    if not _table_exists(old_conn.cursor(), table):
        raise RuntimeError(f"Table '{table}' introuvable dans l'ancienne base.")

    create_sql = _get_create_table_sql(old_conn, table)
    new_cur = new_conn.cursor()
    new_cur.execute(create_sql)

    cols = _get_columns(old_conn, table)
    if not cols:
        return 0

    col_list = ", ".join(cols)
    placeholders = ", ".join(["?"] * len(cols))

    old_cur = old_conn.cursor()
    old_cur.execute(f"SELECT {col_list} FROM {table}")
    rows = old_cur.fetchall()

    new_cur.executemany(
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
        rows,
    )
    new_conn.commit()
    return len(rows)


def _safe_rename_existing_db(path: str) -> None:
    if not os.path.exists(path):
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{path}.bak_{ts}"
    os.replace(path, backup)
    print(f"[OK] Ancienne nouvelle DB sauvegardée: {backup}")


# =========================================================
# CREATE TABLES
# =========================================================
def _create_tables(new_conn: sqlite3.Connection) -> None:
    cur = new_conn.cursor()

    # --- modeles (vers_cc conservé) ---
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS modeles (
            ID_MODELE TEXT PRIMARY KEY,
            Nom_modele TEXT NOT NULL,
            variable_cible TEXT,
            Objectif TEXT,
            Date_creation DATE,
            liste_action TEXT,
            vers_cc TEXT,
            graphe_json TEXT
        );
        """
    )

    # --- cibles ---
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cibles (
            id_cible TEXT PRIMARY KEY,
            nom_cible TEXT NOT NULL,
            date_creation TEXT,
            source TEXT,
            filtre TEXT,
            chemin TEXT
        );
        """
    )

    # --- campagnes ---
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS campagnes (
            id_campagne   TEXT PRIMARY KEY,
            nom_campagne  TEXT NOT NULL,
            id_modele     TEXT NOT NULL,
            id_cible      TEXT NOT NULL,
            date_creation TEXT,
            date_debut    TEXT,
            date_fin      TEXT,
            etat_campagne TEXT
        );
        """
    )

    # --- clients_campagnes ---
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS clients_campagnes (
            ID_CAMPAGNE           TEXT NOT NULL,
            Radical_compte        TEXT NOT NULL,

            statut_avant_campagne TEXT,
            statut_actuel         TEXT,

            Etat_campagne         TEXT,
            NB_jour_campagne      INTEGER,

            ID_Action             TEXT,
            Action                TEXT,

            Last_action           TEXT,
            Resultat_last_action  TEXT,
            Date_last_action      TEXT,
            NB_jour_last_action   INTEGER,

            NB_appel              INTEGER,
            NB_sms                INTEGER,
            NB_mail               INTEGER,
            NB_message            INTEGER,

            PRIMARY KEY (ID_CAMPAGNE, Radical_compte)
        );
        """
    )

    # --- crc_input ---
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS crc_input (
            ID_CAMPAGNE            TEXT NOT NULL,
            Radical_compte         TEXT NOT NULL,

            Numero_Tel             TEXT,
            Mail                   TEXT,

            date_creation_campagne TEXT,
            date_last_action       TEXT,

            ID_Action              TEXT,
            Action                 TEXT,

            Etat_campagne          TEXT,

            statut_avant_campagne  TEXT,
            statut_actuel          TEXT,

            Last_action            TEXT,
            Resultat_last_action   TEXT,

            NB_jour_campagne       INTEGER,
            NB_jour_last_action    INTEGER,

            NB_appel               INTEGER,
            NB_sms                 INTEGER,
            NB_mail                INTEGER,
            NB_message             INTEGER,

            PRIMARY KEY (ID_CAMPAGNE, Radical_compte)
        );
        """
    )

    # --- traitement_mail ---
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS traitement_mail (
            ID_CAMPAGNE            TEXT NOT NULL,
            Radical_compte         TEXT NOT NULL,

            Mail                   TEXT,

            date_creation_campagne TEXT,
            date_last_action       TEXT,

            ID_Action              TEXT,
            Action                 TEXT,

            Etat_campagne          TEXT,

            statut_avant_campagne  TEXT,
            statut_actuel          TEXT,

            Last_action            TEXT,
            Resultat_last_action   TEXT,

            Resultat_transmission  TEXT,
            Date_transmission      TEXT,

            PRIMARY KEY (ID_CAMPAGNE, Radical_compte)
        );
        """
    )

    # --- action_vers_cc ---
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS action_vers_cc (
            radical_compte   TEXT NOT NULL,
            id_campagne      TEXT NOT NULL,

            date_affectation TEXT,
            nb_jour_affecte  INTEGER,

            nom              TEXT,
            prenom           TEXT,
            numero_tel       TEXT,
            adresse_mail     TEXT,
            region           TEXT,
            agence           TEXT,
            gestionnaire     TEXT,

            colonne          TEXT,
            objectif         TEXT,
            traitement       TEXT,

            PRIMARY KEY (id_campagne, radical_compte)
        );
        """
    )

    # --- action_vers_da (clone strict de action_vers_cc) ---
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS action_vers_da (
            radical_compte   TEXT NOT NULL,
            id_campagne      TEXT NOT NULL,

            date_affectation TEXT,
            nb_jour_affecte  INTEGER,

            nom              TEXT,
            prenom           TEXT,
            numero_tel       TEXT,
            adresse_mail     TEXT,
            region           TEXT,
            agence           TEXT,
            gestionnaire     TEXT,

            colonne          TEXT,
            objectif         TEXT,
            traitement       TEXT,

            PRIMARY KEY (id_campagne, radical_compte)
        );
        """
    )

    # INDEXES
    cur.execute("CREATE INDEX IF NOT EXISTS idx_action_vers_cc_camp ON action_vers_cc(id_campagne)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_action_vers_cc_rc ON action_vers_cc(radical_compte)")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_action_vers_da_camp ON action_vers_da(id_campagne)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_action_vers_da_rc ON action_vers_da(radical_compte)")

    new_conn.commit()


# =========================================================
# MAIN
# =========================================================
def main() -> None:
    print("=== REFONTE DB ===")

    if not os.path.exists(OLD_DB):
        raise FileNotFoundError(f"Ancienne base introuvable: {OLD_DB}")

    _safe_rename_existing_db(NEW_DB)

    old_conn = _connect(OLD_DB)
    new_conn = _connect(NEW_DB)

    try:
        _create_tables(new_conn)
        print("[OK] Tables créées")

        n = _copy_table_schema_and_data(old_conn, new_conn, "clients")
        print(f"[OK] Clients importés : {n} lignes")

        cur = new_conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        print("\nTables présentes :")
        for (t,) in cur.fetchall():
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            print(f" - {t}: {cur.fetchone()[0]}")

        print("\n[OK] Refonte DB terminée")

    finally:
        old_conn.close()
        new_conn.close()


if __name__ == "__main__":
    main()
