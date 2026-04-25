from __future__ import annotations

import sqlite3
from app.storage.db import DB_PATH


def column_exists(cur: sqlite3.Cursor, table_name: str, column_name: str) -> bool:
    cur.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cur.fetchall())


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    try:
        if not column_exists(cur, "campagnes", "visitMode"):
            cur.execute("ALTER TABLE campagnes ADD COLUMN visitMode TEXT")
            print("✅ Colonne campagnes.visitMode ajoutée")
        else:
            print("ℹ️ campagnes.visitMode existe déjà")

        if not column_exists(cur, "campagnes", "visitPurpose"):
            cur.execute("ALTER TABLE campagnes ADD COLUMN visitPurpose TEXT")
            print("✅ Colonne campagnes.visitPurpose ajoutée")
        else:
            print("ℹ️ campagnes.visitPurpose existe déjà")

        cur.execute(
            """
            UPDATE campagnes
            SET visitMode = NULL,
                visitPurpose = NULL
            WHERE type_campagne IS NULL
               OR type_campagne != 'avec_action_terrain'
            """
        )

        conn.commit()
        print("🎉 Migration terminée")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()