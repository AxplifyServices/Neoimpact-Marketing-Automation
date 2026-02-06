import sqlite3
from pathlib import Path

DB_PATH = "database.db"   # <-- mets ici le chemin vers ta base
TABLE_NAME = "clients"    # <-- adapte si nécessaire


# Définition des colonnes à ajouter + valeurs possibles
COLUMNS = {
    # Oui / Non
    "App_instaled":           {"type": "TEXT", "allowed": ["Oui", "Non"], "default": "Non"},
    "Premiere_connex":        {"type": "TEXT", "allowed": ["Oui", "Non"], "default": "Non"},
    "carte_dispo_agence":     {"type": "TEXT", "allowed": ["Oui", "Non"], "default": "Non"},
    "carte_retiree":          {"type": "TEXT", "allowed": ["Oui", "Non"], "default": "Non"},
    "Carte_virtuelle":        {"type": "TEXT", "allowed": ["Oui", "Non"], "default": "Non"},
    "Etudiant":               {"type": "TEXT", "allowed": ["Oui", "Non"], "default": "Non"},
    "Dotation_touristique":   {"type": "TEXT", "allowed": ["Oui", "Non"], "default": "Non"},
    "Dotation_ecom":          {"type": "TEXT", "allowed": ["Oui", "Non"], "default": "Non"},
    "Compte_CIH_Mobile":      {"type": "TEXT", "allowed": ["Oui", "Non"], "default": "Non"},
    "Compte_MAD_convertible": {"type": "TEXT", "allowed": ["Oui", "Non"], "default": "Non"},
    "MDM":                    {"type": "TEXT", "allowed": ["Oui", "Non"], "default": "Non"},
    "Presence_maroc":         {"type": "TEXT", "allowed": ["Oui", "Non"], "default": "Non"},
    "BP":                     {"type": "TEXT", "allowed": ["Oui", "Non"], "default": "Non"},
    "chequier_dispo_agence":  {"type": "TEXT", "allowed": ["Oui", "Non"], "default": "Non"},
    "chequier_retire":        {"type": "TEXT", "allowed": ["Oui", "Non"], "default": "Non"},
    "chequier_active":        {"type": "TEXT", "allowed": ["Oui", "Non"], "default": "Non"},

    # Catégorielles
    "Nature_carte": {"type": "TEXT", "allowed": ["MasterCard", "Visa", "CMI"], "default": "MasterCard"},
    "Categorie":    {"type": "TEXT", "allowed": ["Particulier", "Pro/TPE", "Entreprise"], "default": "Particulier"},

    # Numériques
    "Nombre_transaction_inter": {"type": "INTEGER", "allowed": None, "default": 0},
    "Volume_transaction_inter": {"type": "REAL",    "allowed": None, "default": 0.0},
}


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,)
    )
    return cur.fetchone() is not None


def get_existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}  # row[1] = column name


def add_missing_columns(conn: sqlite3.Connection, table: str) -> None:
    existing = get_existing_columns(conn, table)
    for col, meta in COLUMNS.items():
        if col not in existing:
            col_type = meta["type"]
            conn.execute(f'ALTER TABLE {table} ADD COLUMN "{col}" {col_type}')
            print(f"[ADD] {col} {col_type}")


def fill_missing_values(conn: sqlite3.Connection, table: str) -> None:
    """
    Remplit uniquement les valeurs NULL ou '' par la valeur default.
    (Donc pas de risque d’écraser des données déjà présentes.)
    """
    for col, meta in COLUMNS.items():
        default = meta["default"]

        # UPDATE ... WHERE col IS NULL OR col = ''
        # (on garde '' au cas où tes données existantes ont des strings vides)
        conn.execute(
            f'UPDATE {table} '
            f'SET "{col}" = ? '
            f'WHERE "{col}" IS NULL OR TRIM(CAST("{col}" AS TEXT)) = ""',
            (default,)
        )

        # Optionnel: si allowed est défini, on corrige aussi les valeurs invalides (si tu veux)
        # Ici je laisse OFF par défaut pour éviter toute surprise.
        # allowed = meta.get("allowed")
        # if allowed:
        #     placeholders = ",".join(["?"] * len(allowed))
        #     conn.execute(
        #         f'UPDATE {table} SET "{col}" = ? '
        #         f'WHERE "{col}" IS NOT NULL AND TRIM(CAST("{col}" AS TEXT)) != "" '
        #         f'AND "{col}" NOT IN ({placeholders})',
        #         (default, *allowed)
        #     )


def main():
    db_file = Path(DB_PATH)
    if not db_file.exists():
        raise FileNotFoundError(f"DB introuvable: {db_file.resolve()}")

    conn = sqlite3.connect(str(db_file))
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        if not table_exists(conn, TABLE_NAME):
            raise RuntimeError(f"Table introuvable: {TABLE_NAME}")

        add_missing_columns(conn, TABLE_NAME)
        fill_missing_values(conn, TABLE_NAME)

        conn.commit()
        print("[OK] Colonnes ajoutées + valeurs par défaut appliquées (NULL/vides).")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
