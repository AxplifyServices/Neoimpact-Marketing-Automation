# app/scripts/migrate_campagnes_add_description.py
from __future__ import annotations

import os
import sys
import sqlite3
from pathlib import Path


def _resolve_db_path() -> str:
    """
    Résolution robuste du chemin de la DB :
    1) variable d'env DB_PATH si dispo
    2) ./database.db (comme tu l'utilises souvent)
    3) ./app/storage/database.db (fallback)
    """
    env_path = os.getenv("DB_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    candidates = [
        Path.cwd() / "database.db",
        Path.cwd() / "app" / "storage" / "database.db",
    ]
    for p in candidates:
        if p.exists():
            return str(p)

    # Dernier recours : on retourne le premier candidate (créera un fichier vide si lancé sans la bonne DB)
    return str(candidates[0])


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
    return any(r[1] == column_name for r in rows)


def main() -> int:
    # Optionnel: tu peux passer le chemin en argument: python .../migrate_*.py /path/to/db
    db_path = sys.argv[1] if len(sys.argv) > 1 else _resolve_db_path()

    if not Path(db_path).exists():
        print(f"[ERREUR] Base de données introuvable: {db_path}")
        print("=> Passe le chemin en argument, ex: python app/scripts/migrate_...py /chemin/database.db")
        return 1

    print(f"[INFO] DB utilisée: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")

        if not _table_exists(conn, "campagnes"):
            print("[ERREUR] La table 'campagnes' n'existe pas dans cette DB.")
            return 1

        if _column_exists(conn, "campagnes", "description"):
            print("[OK] Colonne 'description' existe déjà dans 'campagnes'. Rien à faire.")
            return 0

        print("[ACTION] Ajout colonne 'description' (TEXT) à la table 'campagnes'...")
        conn.execute("ALTER TABLE campagnes ADD COLUMN description TEXT;")

        # Optionnel mais pratique: éviter les NULL si tu préfères des chaînes vides côté UI/API
        conn.execute("UPDATE campagnes SET description = '' WHERE description IS NULL;")

        conn.commit()
        print("[OK] Migration terminée : colonne 'description' ajoutée.")
        return 0

    except Exception as e:
        conn.rollback()
        print(f"[ERREUR] Migration échouée: {e}")
        return 1

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
