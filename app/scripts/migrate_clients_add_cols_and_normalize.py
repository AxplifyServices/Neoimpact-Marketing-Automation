import os
import sqlite3


# -----------------------------
# CONFIG
# -----------------------------
DEFAULT_DB_PATH = "database.db"
TABLE = "clients"

YES_TOKENS = {"oui", "o", "y", "yes", "true", "1"}
NO_TOKENS  = {"non", "n", "no", "false", "0"}

NEW_COLUMNS = {
    # Oui/Non
    "is_actif_sem": "TEXT",
    "is_actif_mois": "TEXT",
    "is_actif_trois_mois": "TEXT",
    "is_actif_an": "TEXT",

    "is_inactif_sem": "TEXT",
    "is_inactif_mois": "TEXT",
    "is_inactif_trois_mois": "TEXT",
    "is_inactif_an": "TEXT",

    "credit_conso": "TEXT",
    "credit_immo": "TEXT",
    "credit_autre": "TEXT",

    "Eligible_credit": "TEXT",

    # colonnes "actives" (normalisées avec _)
    "Compte_CIH_Mobile_active": "TEXT",
    "Compte_MAD_convertible_active": "TEXT",
    "Carte_virtuelle_active": "TEXT",

    # Numériques
    "Nb_Operation": "REAL",
    "Vol_Operation": "REAL",
}


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def add_missing_columns(conn: sqlite3.Connection, table: str) -> None:
    cols = table_columns(conn, table)
    for col, col_type in NEW_COLUMNS.items():
        if col not in cols:
            print(f"➕ ADD COLUMN {col} {col_type}")
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        else:
            print(f"✔ Column exists: {col}")


def normalize_yes_no_sql(col: str) -> str:
    """
    Convertit une colonne TEXT contenant OUI/NON/Oui/Non/1/0/true/false... vers 'Oui'/'Non'
    Garde NULL si NULL.
    """
    return f"""
    UPDATE {TABLE}
    SET "{col}" = CASE
        WHEN "{col}" IS NULL THEN NULL
        WHEN LOWER(TRIM("{col}")) IN ({",".join(repr(x) for x in YES_TOKENS)}) THEN 'Oui'
        WHEN LOWER(TRIM("{col}")) IN ({",".join(repr(x) for x in NO_TOKENS)}) THEN 'Non'
        WHEN TRIM("{col}") = '' THEN NULL
        ELSE "{col}"  -- valeur inconnue => on laisse (pour audit)
    END
    WHERE "{col}" IS NOT NULL;
    """


def normalize_segment_sql(col: str = "Segment_actuel") -> str:
    """
    Mapping demandé:
    Affluent / En stress / Jeunes / Mass Market / Premium / Medium / Haut de gamme
    + normalisation des valeurs existantes observées (Retail, Mass, Pro, Seniors)
    """
    return f"""
    UPDATE {TABLE}
    SET "{col}" = CASE
        WHEN "{col}" IS NULL OR TRIM("{col}") = '' THEN NULL

        -- déjà conformes (normalisation case)
        WHEN LOWER(TRIM("{col}")) = 'affluent' THEN 'Affluent'
        WHEN LOWER(TRIM("{col}")) IN ('en stress','en_stress','stress') THEN 'En stress'
        WHEN LOWER(TRIM("{col}")) = 'jeunes' THEN 'Jeunes'
        WHEN LOWER(TRIM("{col}")) IN ('mass market','mass_market','massmarket') THEN 'Mass Market'
        WHEN LOWER(TRIM("{col}")) = 'premium' THEN 'Premium'
        WHEN LOWER(TRIM("{col}")) = 'medium' THEN 'Medium'
        WHEN LOWER(TRIM("{col}")) IN ('haut de gamme','haut_de_gamme','hautdegamme') THEN 'Haut de gamme'

        -- valeurs existantes à recoder (best effort)
        WHEN LOWER(TRIM("{col}")) IN ('retail','mass') THEN 'Mass Market'
        WHEN LOWER(TRIM("{col}")) IN ('pro','seniors') THEN 'Medium'

        ELSE "{col}"  -- inconnue => on laisse (audit)
    END
    WHERE "{col}" IS NOT NULL;
    """


def normalize_assurance_sql(col: str = "Assurance_Actuelle") -> str:
    """
    Mapping demandé: Aucune / Immobilier / Vie
    Cas existant: certains enregistrements ont 'Oui'/'Non' -> on mappe:
      - Non => Aucune
      - Oui => Vie (choix générique)
    """
    return f"""
    UPDATE {TABLE}
    SET "{col}" = CASE
        WHEN "{col}" IS NULL OR TRIM("{col}") = '' THEN NULL

        WHEN LOWER(TRIM("{col}")) IN ('aucune','actuelle aucune','actuelle_aucune') THEN 'Aucune'
        WHEN LOWER(TRIM("{col}")) = 'immobilier' THEN 'Immobilier'
        WHEN LOWER(TRIM("{col}")) = 'vie' THEN 'Vie'

        WHEN LOWER(TRIM("{col}")) IN ({",".join(repr(x) for x in YES_TOKENS)}) THEN 'Vie'
        WHEN LOWER(TRIM("{col}")) IN ({",".join(repr(x) for x in NO_TOKENS)}) THEN 'Aucune'

        ELSE "{col}"
    END
    WHERE "{col}" IS NOT NULL;
    """


def normalize_nature_carte_sql(col: str = "Nature_carte") -> str:
    """
    Mapping demandé: CMI / MasterCard / Visa / Aucune
    """
    return f"""
    UPDATE {TABLE}
    SET "{col}" = CASE
        WHEN "{col}" IS NULL OR TRIM("{col}") = '' THEN 'Aucune'
        WHEN LOWER(TRIM("{col}")) IN ('aucune','none','null') THEN 'Aucune'
        WHEN LOWER(TRIM("{col}")) IN ('cmi') THEN 'CMI'
        WHEN LOWER(TRIM("{col}")) IN ('mastercard','master card') THEN 'MasterCard'
        WHEN LOWER(TRIM("{col}")) IN ('visa') THEN 'Visa'
        ELSE "{col}"
    END;
    """


def normalize_qualite_sql(col: str = "Qualite") -> str:
    """
    Mapping demandé: Femme / Homme
    On garde Femme/Homme, et on met NULL pour les valeurs A/B/C (ou autres) car non mappables.
    """
    return f"""
    UPDATE {TABLE}
    SET "{col}" = CASE
        WHEN "{col}" IS NULL OR TRIM("{col}") = '' THEN NULL
        WHEN LOWER(TRIM("{col}")) IN ('femme','f','female') THEN 'Femme'
        WHEN LOWER(TRIM("{col}")) IN ('homme','h','male') THEN 'Homme'
        WHEN LOWER(TRIM("{col}")) IN ('a','b','c') THEN NULL
        ELSE "{col}"
    END
    WHERE "{col}" IS NOT NULL;
    """


def normalize_canal_acq_sql(col: str = "Canal_acquisition") -> str:
    """
    Mapping demandé: Agence / Digital
    """
    return f"""
    UPDATE {TABLE}
    SET "{col}" = CASE
        WHEN "{col}" IS NULL OR TRIM("{col}") = '' THEN NULL
        WHEN LOWER(TRIM("{col}")) = 'agence' THEN 'Agence'
        WHEN LOWER(TRIM("{col}")) = 'digital' THEN 'Digital'
        ELSE "{col}"
    END
    WHERE "{col}" IS NOT NULL;
    """


def run(db_path: str) -> None:
    conn = connect(db_path)
    try:
        print(f"DB: {db_path}")

        # 1) Add columns
        add_missing_columns(conn, TABLE)

        # 2) Normalize existing columns (only if column exists)
        cols = table_columns(conn, TABLE)

        # Oui/Non columns to normalize (existing ones)
        yesno_existing = [
            "Epargne",
            "Dossier_Complet",
            "Validation_KYC",
            "Activation_du_compte",
            "Activation_carte",
            "Compte_CIH_Mobile",
        ]
        for c in yesno_existing:
            if c in cols:
                print(f"🔧 Normalize Yes/No: {c}")
                conn.executescript(normalize_yes_no_sql(c))

        # Segment
        if "Segment_actuel" in cols:
            print("🔧 Normalize Segment_actuel")
            conn.executescript(normalize_segment_sql("Segment_actuel"))

        # Assurance
        if "Assurance_Actuelle" in cols:
            print("🔧 Normalize Assurance_Actuelle")
            conn.executescript(normalize_assurance_sql("Assurance_Actuelle"))

        # Nature carte
        if "Nature_carte" in cols:
            print("🔧 Normalize Nature_carte")
            conn.executescript(normalize_nature_carte_sql("Nature_carte"))

        # Qualite
        if "Qualite" in cols:
            print("🔧 Normalize Qualite")
            conn.executescript(normalize_qualite_sql("Qualite"))

        # Canal acquisition
        if "Canal_acquisition" in cols:
            print("🔧 Normalize Canal_acquisition")
            conn.executescript(normalize_canal_acq_sql("Canal_acquisition"))

        conn.commit()
        print("✅ Migration done.")
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = os.getenv("MA_DB_PATH") or DEFAULT_DB_PATH
    run(db_path)