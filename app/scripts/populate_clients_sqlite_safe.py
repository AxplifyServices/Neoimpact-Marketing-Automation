import random
import sqlite3
from faker import Faker

# =========================
# CONFIG
# =========================
TARGET_TOTAL = 5000
DB_PATH = "clients.db"
SEED = 42

random.seed(SEED)
fake = Faker("fr_FR")
Faker.seed(SEED)

# =========================
# LISTES METIER
# =========================
STATUTS = ["Actif", "Inactif", "Prospect", "Rupture de relation"]
QUALITES = ["Homme", "Femme"]
CANAL_ACQ = ["Agence", "Digital"]
SEGMENTS = ["Mass Market", "Retail", "Affluent", "Premium", "Pro", "Jeunes", "Seniors"]
CARTES = ["Silver", "Gold", "Standard", "Black", "Aucune"]
ASSURANCES = ["Immobilier", "Vie", "Aucune"]
REGIONS = [
    "Casablanca-Settat", "Rabat-Salé-Kénitra", "Marrakech-Safi",
    "Fès-Meknès", "Tanger-Tétouan-Al Hoceïma", "Souss-Massa",
    "Oriental", "Béni Mellal-Khénifra", "Drâa-Tafilalet"
]
GESTIONNAIRES = [
    "A. El Amrani", "S. Benjelloun", "M. El Idrissi",
    "N. Ait Lahcen", "H. Bennis", "K. Tahiri"
]

# =========================
# SQL
# =========================
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS clients (
    radical_compte TEXT PRIMARY KEY,
    Nom TEXT,
    Prenom TEXT,
    ID_Client TEXT UNIQUE,
    STATUT_CLIENT TEXT,
    Age INTEGER,
    Qualite TEXT,
    Anciennete INTEGER,
    Region TEXT,
    Agence TEXT,
    Gestionnaire TEXT,
    Dossier_Complet TEXT,
    Validation_KYC TEXT,
    Activation_du_compte TEXT,
    Activation_carte TEXT,
    Canal_acquisition TEXT,
    Segment_actuel TEXT,
    Numero_Tel TEXT,
    Mail TEXT,
    Epargne TEXT,
    Carte_Actuelle TEXT,
    Assurance_Actuelle TEXT
);
"""

INSERT_SQL = """
INSERT INTO clients VALUES (
    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
);
"""

# =========================
# HELPERS
# =========================
def gen_maroc_phone():
    return "+212" + random.choice(["6", "7"]) + "".join(str(random.randint(0, 9)) for _ in range(8))

def yes_no(p):
    return "OUI" if random.random() < p else "NON"

# =========================
# MAIN
# =========================
def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Création table si absente
    cur.execute(CREATE_TABLE_SQL)

    # Combien de clients existent déjà ?
    cur.execute("SELECT COUNT(*) FROM clients")
    current_count = cur.fetchone()[0]

    if current_count >= TARGET_TOTAL:
        print(f"✔ Base déjà complète ({current_count} clients). Aucune action.")
        return

    to_generate = TARGET_TOTAL - current_count
    print(f"➡ Génération de {to_generate} nouveaux clients (base existante = {current_count})")

    rows = []

    for i in range(current_count + 1, TARGET_TOTAL + 1):
        radical = f"RC{i:08d}"
        id_client = f"CL{i:08d}"

        qualite = random.choice(QUALITES)
        prenom = fake.first_name_male() if qualite == "Homme" else fake.first_name_female()
        nom = fake.last_name()

        age = random.randint(18, 85)
        anciennete = random.randint(0, min(40, age - 18))
        statut = random.choice(STATUTS)

        dossier = yes_no(0.8 if statut == "Actif" else 0.4)
        kyc = "OUI" if dossier == "OUI" and random.random() < 0.8 else "NON"

        row = (
            radical,
            nom,
            prenom,
            id_client,
            statut,
            age,
            qualite,
            anciennete,
            random.choice(REGIONS),
            "Agence Centrale",
            random.choice(GESTIONNAIRES),
            dossier,
            kyc,
            yes_no(0.8),
            yes_no(0.7),
            random.choice(CANAL_ACQ),
            random.choice(SEGMENTS),
            gen_maroc_phone(),
            f"{prenom.lower()}.{nom.lower()}@gmail.com",
            yes_no(0.5),
            random.choice(CARTES),
            random.choice(ASSURANCES),
        )
        rows.append(row)

    cur.executemany(INSERT_SQL, rows)
    conn.commit()
    conn.close()

    print(f"✅ {to_generate} clients ajoutés avec succès.")

if __name__ == "__main__":
    main()
