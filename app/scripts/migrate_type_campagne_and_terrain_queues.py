from __future__ import annotations

import sqlite3
from pathlib import Path


DB_PATH = Path("database.db")  # adapte si ton fichier sqlite n'est pas ici


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


def column_exists(cur: sqlite3.Cursor, table_name: str, column_name: str) -> bool:
    cur.execute(f"PRAGMA table_info({table_name})")
    cols = cur.fetchall()
    return any(str(col[1]).strip().lower() == column_name.strip().lower() for col in cols)


def ensure_type_campagne_column(cur: sqlite3.Cursor) -> None:
    if not column_exists(cur, "campagnes", "type_campagne"):
        cur.execute(
            """
            ALTER TABLE campagnes
            ADD COLUMN type_campagne TEXT DEFAULT 'sans_action_terrain'
            """
        )
        print("✅ Colonne campagnes.type_campagne ajoutée")
    else:
        print("ℹ️ Colonne campagnes.type_campagne déjà présente")


def normalize_existing_campagnes(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """
        UPDATE campagnes
        SET type_campagne = 'sans_action_terrain'
        WHERE type_campagne IS NULL
           OR TRIM(type_campagne) = ''
           OR TRIM(type_campagne) NOT IN ('sans_action_terrain', 'avec_action_terrain')
        """
    )
    print(f"✅ Campagnes normalisées: {cur.rowcount}")


def ensure_vers_da_terrain_table(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS vers_da_terrain (
            ID_CAMPAGNE            TEXT NOT NULL,
            Radical_compte         TEXT NOT NULL,
            Numero_Tel             TEXT,
            Mail                   TEXT,
            date_creation_campagne TEXT,
            date_last_action       TEXT,
            ID_Action              TEXT,
            Canal                  TEXT,
            Action                 TEXT,
            Etat_campagne          TEXT,
            statut_avant_campagne  TEXT,
            statut_actuel          TEXT,
            PRIMARY KEY (ID_CAMPAGNE, Radical_compte)
        )
        """
    )
    print("✅ Table vers_da_terrain prête")


def ensure_vers_cc_terrain_table(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS vers_cc_terrain (
            ID_CAMPAGNE            TEXT NOT NULL,
            Radical_compte         TEXT NOT NULL,
            Numero_Tel             TEXT,
            Mail                   TEXT,
            date_creation_campagne TEXT,
            date_last_action       TEXT,
            ID_Action              TEXT,
            Canal                  TEXT,
            Action                 TEXT,
            Etat_campagne          TEXT,
            statut_avant_campagne  TEXT,
            statut_actuel          TEXT,
            PRIMARY KEY (ID_CAMPAGNE, Radical_compte)
        )
        """
    )
    print("✅ Table vers_cc_terrain prête")


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Base SQLite introuvable: {DB_PATH.resolve()}")

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    try:
        if not table_exists(cur, "campagnes"):
            raise RuntimeError("La table campagnes est introuvable")

        ensure_type_campagne_column(cur)
        normalize_existing_campagnes(cur)
        ensure_vers_da_terrain_table(cur)
        ensure_vers_cc_terrain_table(cur)

        conn.commit()
        print("🎉 Migration terminée avec succès")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()