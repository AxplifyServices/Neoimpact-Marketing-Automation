from __future__ import annotations

import os
import sqlite3
from typing import List


# -----------------------------
# Config
# -----------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "clients.db")

# Tables à NE PAS toucher
KEEP_TABLES = {"clients", "cibles"}

# Tables à vider (tu peux en ajouter ici)
TABLES_TO_CLEAR: List[str] = [
    "clients_campagnes",
    "campagnes",
    "modeles",
    "crc_output",
    "crc_input",
    "traitement_mail",
    "action_vers_cc",
    # ajoute ici toute autre table "métier" que tu veux vider
]


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cur.fetchone() is not None


def clear_tables(db_path: str) -> None:
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Base introuvable: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = OFF;")  # évite erreurs FK si présentes
        cur = conn.cursor()

        # Safety: ne jamais supprimer clients / cibles
        safe_tables = [t for t in TABLES_TO_CLEAR if t not in KEEP_TABLES]

        existing = [t for t in safe_tables if table_exists(conn, t)]
        missing = [t for t in safe_tables if t not in existing]

        print("DB:", db_path)
        print("KEEP:", sorted(list(KEEP_TABLES)))
        print("WILL CLEAR (existing):", existing)
        if missing:
            print("SKIP (missing):", missing)

        cur.execute("BEGIN;")
        for t in existing:
            # DELETE est plus sûr que DROP (tu gardes les schémas)
            cur.execute(f"DELETE FROM {t};")
        cur.execute("COMMIT;")

        # Optionnel: si tu veux aussi reset les AUTOINCREMENT
        # (SQLite garde parfois les compteurs dans sqlite_sequence)
        if table_exists(conn, "sqlite_sequence"):
            cur.execute("BEGIN;")
            for t in existing:
                cur.execute("DELETE FROM sqlite_sequence WHERE name=?;", (t,))
            cur.execute("COMMIT;")

        print("✅ Nettoyage terminé.")
    except Exception:
        try:
            conn.execute("ROLLBACK;")
        except Exception:
            pass
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    clear_tables(DB_PATH)
