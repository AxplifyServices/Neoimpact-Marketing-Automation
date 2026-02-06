import sqlite3
import random
import re
from pathlib import Path

DB_PATH = "database.db"     # <-- adapte si besoin
TABLE = "clients"
N_ROWS = 500

# --- Modalités ---
OUI_NON = ["Oui", "Non"]
CANAL_ACQ = ["Agence", "Digital"]
STATUT_CLIENT = ["Actif", "Inactif", "Prospect", "Rupture de relation"]
ASSURANCE = ["Immobilier", "Vie", "Aucune"]

# Carte actuelle : inclut les nouvelles valeurs
CARTE_ACTUELLE = ["Aucune", "Gold", "Standard", "Silver", "Black", "Code 30", "Code 212"]

NATURE_CARTE = ["MasterCard", "Visa", "CMI"]
CATEGORIE = ["Particulier", "Pro/TPE", "Entreprise"]

# (petites listes pour générer des données “propres”)
PRENOMS = ["Youssef", "Sara", "Imane", "Khalid", "Nadia", "Omar", "Salma", "Hamza", "Aya", "Mehdi"]
NOMS = ["El Amrani", "Benali", "Alaoui", "El Idrissi", "Kabbaj", "Berrada", "Chraibi", "Rami", "Saidi", "Haddad"]
REGIONS = ["Casablanca-Settat", "Rabat-Salé-Kénitra", "Marrakech-Safi", "Fès-Meknès", "Tanger-Tétouan-Al Hoceïma"]
AGENCES = ["AG001", "AG002", "AG003", "AG010", "AG020"]
GESTIONNAIRES = ["GS001", "GS002", "GS003", "GS010", "GS020"]
SEGMENTS = ["Mass", "Affluent", "Premium", "Jeunes", "Pro"]

# --- Nouvelles colonnes à ajouter (si absentes) ---
# Attention: ta DB actuelle utilise des noms CamelCase/underscore (ex: Dossier_Complet, Carte_Actuelle)
NEW_COLUMNS = {
    "App_instaled": ("TEXT", "Non"),
    "Premiere_connex": ("TEXT", "Non"),
    "carte_dispo_agence": ("TEXT", "Non"),
    "carte_retiree": ("TEXT", "Non"),
    "Carte_virtuelle": ("TEXT", "Non"),
    "Nature_carte": ("TEXT", "MasterCard"),
    "Etudiant": ("TEXT", "Non"),
    "Dotation_touristique": ("TEXT", "Non"),
    "Dotation_ecom": ("TEXT", "Non"),
    "Nombre_transaction_inter": ("INTEGER", 0),
    "Volume_transaction_inter": ("REAL", 0.0),
    "Compte_CIH_Mobile": ("TEXT", "Non"),
    "Compte_MAD_convertible": ("TEXT", "Non"),
    "MDM": ("TEXT", "Non"),
    "Presence_maroc": ("TEXT", "Non"),
    "BP": ("TEXT", "Non"),
    "Categorie": ("TEXT", "Particulier"),
    "chequier_dispo_agence": ("TEXT", "Non"),
    "chequier_retire": ("TEXT", "Non"),
    "chequier_active": ("TEXT", "Non"),
}

# --- Helpers ---
def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    r = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)).fetchone()
    return r is not None

def get_cols(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]

def add_missing_columns(conn: sqlite3.Connection, table: str) -> None:
    existing = set(get_cols(conn, table))
    for col, (ctype, default_val) in NEW_COLUMNS.items():
        if col not in existing:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN "{col}" {ctype}')
            # Remplir immédiatement les NULL/vides
            conn.execute(
                f'UPDATE {table} SET "{col}"=? WHERE "{col}" IS NULL OR TRIM(CAST("{col}" AS TEXT))=""',
                (default_val,)
            )
            print(f"[ADD] {col} ({ctype})")

def max_suffix(conn: sqlite3.Connection, table: str, col: str, prefix: str) -> int:
    rows = conn.execute(
        f"SELECT {col} FROM {table} WHERE {col} LIKE ?",
        (prefix + "%",)
    ).fetchall()
    mx = 0
    for (v,) in rows:
        if not v:
            continue
        m = re.match(re.escape(prefix) + r"(\d+)$", str(v))
        if m:
            mx = max(mx, int(m.group(1)))
    return mx

def mk_phone() -> str:
    # Maroc: 06/07 + 8 chiffres
    start = random.choice(["06", "07"])
    return start + "".join(random.choice("0123456789") for _ in range(8))

def mk_email(prenom: str, nom: str, i: int) -> str:
    base = (prenom + "." + nom).lower().replace(" ", "").replace("'", "")
    return f"{base}{i}@example.com"

def yn(p_yes=0.5) -> str:
    return "Oui" if random.random() < p_yes else "Non"

def rand_int(a, b) -> int:
    return random.randint(a, b)

def rand_float(a, b, nd=2) -> float:
    return round(random.uniform(a, b), nd)

def pick_carte_actuelle(i: int) -> str:
    # pour être sûr que Code 30 et Code 212 apparaissent dans les 500 lignes
    if i == 0:
        return "Code 30"
    if i == 1:
        return "Code 212"
    # ensuite tirage avec un petit boost sur les codes
    weights = {
        "Aucune": 0.25,
        "Standard": 0.20,
        "Silver": 0.15,
        "Gold": 0.15,
        "Black": 0.10,
        "Code 30": 0.075,
        "Code 212": 0.075,
    }
    items = list(weights.keys())
    w = list(weights.values())
    return random.choices(items, weights=w, k=1)[0]

def main():
    db = Path(DB_PATH)
    if not db.exists():
        raise FileNotFoundError(f"DB introuvable: {db.resolve()}")

    conn = sqlite3.connect(str(db))
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        if not table_exists(conn, TABLE):
            raise RuntimeError(f"Table introuvable: {TABLE}")

        # 1) Ajout colonnes manquantes
        add_missing_columns(conn, TABLE)

        cols = set(get_cols(conn, TABLE))

        # 2) Calcul des prochains IDs uniques
        max_rc = max_suffix(conn, TABLE, "radical_compte", "RC")
        max_cl = max_suffix(conn, TABLE, "ID_Client", "CL")

        # 3) Construction des lignes à insérer (on insère uniquement les colonnes existantes)
        # Colonnes "de base" (existantes dans ta DB actuelle)
        base_fields = [
            "radical_compte", "Nom", "Prenom", "ID_Client", "Numero_Tel", "Mail",
            "Canal_acquisition", "Age", "Qualite", "Anciennete", "Region", "Agence",
            "Gestionnaire", "STATUT_CLIENT", "Dossier_Complet", "Validation_KYC",
            "Activation_du_compte", "Activation_carte", "Segment_actuel", "Epargne",
            "Carte_Actuelle", "Assurance_Actuelle",
            "nb_transaction", "vol_transaction",
            "nb_retrait_gab", "vol_retrait_gab",
            "nb_transaction_ecom", "vol_transaction_ecom",
            "nb_virement", "vol_virement",
            "solde_moyen_depots", "encours_moyen", "encours_global", "encours_conso",
            "encours_immo", "revenu_domicilie", "montant_revenu"
        ]

        # Nouvelles colonnes (si elles existent désormais)
        new_fields = list(NEW_COLUMNS.keys())

        # On ne garde que les champs réellement présents dans la table
        fields = [f for f in base_fields + new_fields if f in cols]

        placeholders = ",".join(["?"] * len(fields))
        columns_sql = ",".join([f'"{c}"' for c in fields])   # <-- guillemets SQL propres
        sql = f'INSERT INTO "{TABLE}" ({columns_sql}) VALUES ({placeholders})'


        rows = []
        for i in range(N_ROWS):
            rc_num = max_rc + i + 1
            cl_num = max_cl + i + 1
            radical_compte = f"RC{rc_num:08d}"
            id_client = f"CL{cl_num:08d}"

            prenom = random.choice(PRENOMS)
            nom = random.choice(NOMS)
            tel = mk_phone()
            mail = mk_email(prenom, nom, cl_num)

            # Champs base
            data = {
                "radical_compte": radical_compte,
                "Nom": nom,
                "Prenom": prenom,
                "ID_Client": id_client,
                "Numero_Tel": tel,
                "Mail": mail,
                "Canal_acquisition": random.choice(CANAL_ACQ),
                "Age": rand_int(18, 75),
                "Qualite": random.choice(["A", "B", "C"]),
                "Anciennete": rand_int(0, 30),
                "Region": random.choice(REGIONS),
                "Agence": random.choice(AGENCES),
                "Gestionnaire": random.choice(GESTIONNAIRES),
                "STATUT_CLIENT": random.choice(STATUT_CLIENT),
                "Dossier_Complet": yn(0.65),
                "Validation_KYC": yn(0.7),
                "Activation_du_compte": yn(0.8),
                "Activation_carte": yn(0.75),
                "Segment_actuel": random.choice(SEGMENTS),
                "Epargne": yn(0.4),
                "Carte_Actuelle": pick_carte_actuelle(i),
                "Assurance_Actuelle": random.choice(ASSURANCE),

                "nb_transaction": rand_int(0, 400),
                "vol_transaction": rand_float(0, 250000),
                "nb_retrait_gab": rand_int(0, 80),
                "vol_retrait_gab": rand_float(0, 60000),
                "nb_transaction_ecom": rand_int(0, 120),
                "vol_transaction_ecom": rand_float(0, 150000),
                "nb_virement": rand_int(0, 60),
                "vol_virement": rand_float(0, 300000),

                "solde_moyen_depots": rand_float(0, 500000),
                "encours_moyen": rand_float(0, 800000),
                "encours_global": rand_float(0, 1200000),
                "encours_conso": rand_float(0, 400000),
                "encours_immo": rand_float(0, 900000),
                "revenu_domicilie": yn(0.5),
                "montant_revenu": rand_float(0, 120000),
            }

            # Champs nouveaux
            if "Nature_carte" in cols:
                data["Nature_carte"] = random.choice(NATURE_CARTE)
            if "Categorie" in cols:
                data["Categorie"] = random.choice(CATEGORIE)

            for yn_col in [
                "App_instaled","Premiere_connex","carte_dispo_agence","carte_retiree","Carte_virtuelle",
                "Etudiant","Dotation_touristique","Dotation_ecom","Compte_CIH_Mobile","Compte_MAD_convertible",
                "MDM","Presence_maroc","BP","chequier_dispo_agence","chequier_retire","chequier_active"
            ]:
                if yn_col in cols:
                    data[yn_col] = yn(0.5)

            if "Nombre_transaction_inter" in cols:
                data["Nombre_transaction_inter"] = rand_int(0, 80)
            if "Volume_transaction_inter" in cols:
                data["Volume_transaction_inter"] = rand_float(0, 120000)

            row = [data.get(f) for f in fields]
            rows.append(row)

        # Insert batch
        conn.executemany(sql, rows)
        conn.commit()

        print(f"[OK] {N_ROWS} lignes ajoutées dans {TABLE}.")
        print(f"[INFO] Exemple Carte_Actuelle insérée: Code 30, Code 212 + autres modalités.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
