from __future__ import annotations

import argparse
import hashlib
import os
import random
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg import sql
from dotenv import load_dotenv
from faker import Faker


# ============================================================
# CONFIGURATION DETERMINISTE
# ============================================================

DEFAULT_ROWS = 500_000
DEFAULT_SEED = 20260816

TABLE = "clients"
STAGE_TABLE = "_seed_clients_stage"

# Préfixes volontairement réservés aux données Faker.
# Ils permettent de rejouer le seed sans entrer en collision avec
# des clients métier existants.
RADICAL_PREFIX = "FAKE_RC_"
CLIENT_PREFIX = "FAKE_CL_"

# ============================================================
# MODALITES CATEGORIELLES
# Source principale :
# app/api/routers/data_admin.py -> CATEGORICAL_MAPPING
# ============================================================

YES_NO = ["Oui", "Non"]

STATUT_CLIENT = ["Actif", "Inactif", "Prospect", "Rupture de relation"]
QUALITE = ["Femme", "Homme"]
CANAL_ACQUISITION = ["Agence", "Digital"]

SEGMENT_ACTUEL = [
    "Affluent",
    "En stress",
    "Jeunes",
    "Mass Market",
    "Premium",
    "Medium",
    "Haut de gamme",
]

ASSURANCE_ACTUELLE = ["Aucune", "Immobilier", "Vie"]
NATURE_CARTE = ["CMI", "MasterCard", "Visa", "Aucune"]

CARTE_ACTUELLE = [
    "Aucune",
    "Black",
    "Classic",
    "Code 212",
    "Code 30",
    "Gold",
    "Silver",
    "Standard",
]

CATEGORIE = ["Entreprise", "Particulier", "Pro/TPE"]

# Ces trois champs n'ont pas de mapping hardcodé dans data_admin.py.
# On reprend donc les modalités explicites présentes dans les anciens
# générateurs de données du projet.
REGIONS = [
    "Casablanca-Settat",
    "Rabat-Salé-Kénitra",
    "Marrakech-Safi",
    "Fès-Meknès",
    "Tanger-Tétouan-Al Hoceïma",
    "Souss-Massa",
    "Oriental",
    "Béni Mellal-Khénifra",
    "Drâa-Tafilalet",
]

AGENCES = ["AG001", "AG002", "AG003", "AG010", "AG020"]

GESTIONNAIRES = [
    "A. El Amrani",
    "S. Benjelloun",
    "M. El Idrissi",
    "N. Ait Lahcen",
    "H. Bennis",
    "K. Tahiri",
]

# ============================================================
# BORNES NUMERIQUES
# Source : anciens scripts de génération présents dans le projet.
#
# Les champs agrégés Nb_Operation / Vol_Operation sont dérivés plus bas
# au lieu d'être tirés indépendamment.
# ============================================================

NUMERIC_BOUNDS = {
    "Age": (18, 85),
    "Anciennete": (0, 40),  # bornée ensuite par Age - 18

    "nb_transaction": (0, 400),
    "vol_transaction": (0.0, 250_000.0),

    "nb_retrait_gab": (0, 80),
    "vol_retrait_gab": (0.0, 60_000.0),

    "nb_transaction_ecom": (0, 120),
    "vol_transaction_ecom": (0.0, 150_000.0),

    "nb_virement": (0, 60),
    "vol_virement": (0.0, 300_000.0),

    "solde_moyen_depots": (0.0, 500_000.0),
    "encours_moyen": (0.0, 800_000.0),
    "encours_global": (0.0, 1_200_000.0),
    "encours_conso": (0.0, 400_000.0),
    "encours_immo": (0.0, 900_000.0),

    "montant_revenu": (0.0, 120_000.0),

    "Nombre_transaction_inter": (0, 80),
    "Volume_transaction_inter": (0.0, 120_000.0),
}


# ============================================================
# COLONNES
# Correspond exactement au schéma PostgreSQL clients actuel.
# ============================================================

COLUMNS = [
    "radical_compte",
    "Nom",
    "Prenom",
    "ID_Client",
    "STATUT_CLIENT",
    "Age",
    "Qualite",
    "Anciennete",
    "Region",
    "Agence",
    "Gestionnaire",
    "Dossier_Complet",
    "Validation_KYC",
    "Activation_du_compte",
    "Activation_carte",
    "Canal_acquisition",
    "Segment_actuel",
    "Numero_Tel",
    "Mail",
    "Epargne",
    "Carte_Actuelle",
    "Assurance_Actuelle",
    "nb_transaction",
    "vol_transaction",
    "nb_retrait_gab",
    "vol_retrait_gab",
    "nb_transaction_ecom",
    "vol_transaction_ecom",
    "nb_virement",
    "vol_virement",
    "solde_moyen_depots",
    "encours_moyen",
    "encours_global",
    "encours_conso",
    "encours_immo",
    "revenu_domicilie",
    "montant_revenu",
    "App_instaled",
    "Premiere_connex",
    "carte_dispo_agence",
    "carte_retiree",
    "Carte_virtuelle",
    "Etudiant",
    "Dotation_touristique",
    "Dotation_ecom",
    "Compte_CIH_Mobile",
    "Compte_MAD_convertible",
    "MDM",
    "Presence_maroc",
    "BP",
    "chequier_dispo_agence",
    "chequier_retire",
    "chequier_active",
    "Nature_carte",
    "Categorie",
    "Nombre_transaction_inter",
    "Volume_transaction_inter",
    "is_actif_sem",
    "is_actif_mois",
    "is_actif_trois_mois",
    "is_actif_an",
    "is_inactif_sem",
    "is_inactif_mois",
    "is_inactif_trois_mois",
    "is_inactif_an",
    "credit_conso",
    "credit_immo",
    "credit_autre",
    "Eligible_credit",
    "Compte_CIH_Mobile_active",
    "Compte_MAD_convertible_active",
    "Carte_virtuelle_active",
    "Nb_Operation",
    "Vol_Operation",
]


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_environment() -> None:
    # En local : charge le .env du repo.
    # Dans Docker : les variables du conteneur existent déjà et gardent
    # la priorité (override=False).
    load_dotenv(project_root() / ".env", override=False)


def database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL est absent. "
            "Le script utilise le même .env que l'application."
        )
    return url


def normalize_email_part(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return (
        ascii_value.lower()
        .replace(" ", "")
        .replace("'", "")
        .replace("-", "")
        .replace(".", "")
    )


def yn(rng: random.Random, probability_yes: float = 0.5) -> str:
    return "Oui" if rng.random() < probability_yes else "Non"


def randint(rng: random.Random, name: str) -> int:
    lo, hi = NUMERIC_BOUNDS[name]
    return rng.randint(int(lo), int(hi))


def randfloat(rng: random.Random, name: str) -> float:
    lo, hi = NUMERIC_BOUNDS[name]
    return round(rng.uniform(float(lo), float(hi)), 2)


def weighted_choice(rng: random.Random, values: list[str], weights: list[float]) -> str:
    return rng.choices(values, weights=weights, k=1)[0]


def build_client(
    i: int,
    rng: random.Random,
    fake: Faker,
) -> tuple[Any, ...]:
    # --------------------------------------------------------
    # Identité
    # --------------------------------------------------------
    radical_compte = f"{RADICAL_PREFIX}{i:09d}"
    id_client = f"{CLIENT_PREFIX}{i:09d}"

    qualite = weighted_choice(rng, QUALITE, [0.50, 0.50])

    if qualite == "Homme":
        prenom = fake.first_name_male()
    else:
        prenom = fake.first_name_female()

    nom = fake.last_name()

    numero_tel = "+212" + rng.choice(["6", "7"]) + "".join(
        str(rng.randint(0, 9)) for _ in range(8)
    )

    email = (
        f"{normalize_email_part(prenom)}."
        f"{normalize_email_part(nom)}."
        f"{i:09d}@faker.axplitest.local"
    )

    # --------------------------------------------------------
    # Profil client
    # --------------------------------------------------------
    age = randint(rng, "Age")
    anciennete_max = min(int(NUMERIC_BOUNDS["Anciennete"][1]), max(0, age - 18))
    anciennete = rng.randint(0, anciennete_max)

    statut = weighted_choice(
        rng,
        STATUT_CLIENT,
        [0.68, 0.13, 0.14, 0.05],
    )

    segment = weighted_choice(
        rng,
        SEGMENT_ACTUEL,
        [0.11, 0.07, 0.17, 0.31, 0.10, 0.16, 0.08],
    )

    canal = weighted_choice(rng, CANAL_ACQUISITION, [0.57, 0.43])
    region = rng.choice(REGIONS)
    agence = rng.choice(AGENCES)
    gestionnaire = rng.choice(GESTIONNAIRES)

    # Cohérence dossier / KYC / activation.
    dossier_probability = {
        "Actif": 0.94,
        "Inactif": 0.86,
        "Prospect": 0.48,
        "Rupture de relation": 0.76,
    }[statut]
    dossier_complet = yn(rng, dossier_probability)

    kyc_probability = 0.93 if dossier_complet == "Oui" else 0.22
    validation_kyc = yn(rng, kyc_probability)

    account_probability = {
        "Actif": 0.97,
        "Inactif": 0.93,
        "Prospect": 0.30,
        "Rupture de relation": 0.94,
    }[statut]
    activation_compte = yn(rng, account_probability)

    # --------------------------------------------------------
    # Revenu / épargne / crédit
    # --------------------------------------------------------
    revenu_probability = {
        "Affluent": 0.82,
        "En stress": 0.48,
        "Jeunes": 0.35,
        "Mass Market": 0.58,
        "Premium": 0.88,
        "Medium": 0.68,
        "Haut de gamme": 0.94,
    }[segment]
    revenu_domicilie = yn(rng, revenu_probability)

    # On conserve la borne métier trouvée dans le code.
    # Le segment influe seulement sur la distribution à l'intérieur de cette borne.
    max_revenu = float(NUMERIC_BOUNDS["montant_revenu"][1])
    segment_income_factor = {
        "Affluent": 0.80,
        "En stress": 0.28,
        "Jeunes": 0.22,
        "Mass Market": 0.38,
        "Premium": 0.72,
        "Medium": 0.52,
        "Haut de gamme": 1.00,
    }[segment]
    revenu_cap = max(3_000.0, max_revenu * segment_income_factor)
    montant_revenu = round(rng.triangular(0.0, revenu_cap, revenu_cap * 0.42), 2)

    epargne = yn(
        rng,
        min(0.90, 0.20 + (montant_revenu / max_revenu) * 0.65),
    )

    # --------------------------------------------------------
    # Cartes / assurance
    # --------------------------------------------------------
    carte_actuelle = weighted_choice(
        rng,
        CARTE_ACTUELLE,
        [0.20, 0.04, 0.18, 0.08, 0.07, 0.12, 0.14, 0.17],
    )

    if carte_actuelle == "Aucune":
        nature_carte = "Aucune"
        activation_carte = "Non"
    else:
        nature_carte = weighted_choice(
            rng,
            ["CMI", "MasterCard", "Visa"],
            [0.20, 0.38, 0.42],
        )
        activation_carte = yn(rng, 0.90 if statut == "Actif" else 0.67)

    assurance = weighted_choice(
        rng,
        ASSURANCE_ACTUELLE,
        [0.64, 0.19, 0.17],
    )

    categorie = weighted_choice(
        rng,
        CATEGORIE,
        [0.09, 0.76, 0.15],
    )

    # --------------------------------------------------------
    # Activité transactionnelle
    # --------------------------------------------------------
    activity_factor = {
        "Actif": rng.uniform(0.55, 1.00),
        "Inactif": rng.uniform(0.00, 0.18),
        "Prospect": rng.uniform(0.00, 0.08),
        "Rupture de relation": rng.uniform(0.00, 0.05),
    }[statut]

    def activity_int(name: str) -> int:
        lo, hi = NUMERIC_BOUNDS[name]
        return int(round(rng.uniform(float(lo), float(hi) * activity_factor)))

    def activity_float(name: str) -> float:
        lo, hi = NUMERIC_BOUNDS[name]
        return round(rng.uniform(float(lo), float(hi) * activity_factor), 2)

    nb_transaction = activity_int("nb_transaction")
    vol_transaction = activity_float("vol_transaction")

    nb_retrait_gab = activity_int("nb_retrait_gab")
    vol_retrait_gab = activity_float("vol_retrait_gab")

    nb_transaction_ecom = activity_int("nb_transaction_ecom")
    vol_transaction_ecom = activity_float("vol_transaction_ecom")

    nb_virement = activity_int("nb_virement")
    vol_virement = activity_float("vol_virement")

    nombre_transaction_inter = activity_int("Nombre_transaction_inter")
    volume_transaction_inter = activity_float("Volume_transaction_inter")

    nb_operation = float(
        nb_transaction
        + nb_retrait_gab
        + nb_transaction_ecom
        + nb_virement
        + nombre_transaction_inter
    )
    vol_operation = round(
        vol_transaction
        + vol_retrait_gab
        + vol_transaction_ecom
        + vol_virement
        + volume_transaction_inter,
        2,
    )

    # --------------------------------------------------------
    # Soldes / encours
    # --------------------------------------------------------
    solde_moyen_depots = randfloat(rng, "solde_moyen_depots")

    encours_conso = randfloat(rng, "encours_conso")
    encours_immo = randfloat(rng, "encours_immo")

    # Encours global reste dans la borne du projet et reste cohérent
    # avec les sous-encours lorsque cela est possible.
    encours_global_raw = (
        encours_conso
        + encours_immo
        + rng.uniform(0.0, 120_000.0)
    )
    encours_global = round(
        min(float(NUMERIC_BOUNDS["encours_global"][1]), encours_global_raw),
        2,
    )

    encours_moyen = round(
        min(
            float(NUMERIC_BOUNDS["encours_moyen"][1]),
            encours_global * rng.uniform(0.25, 0.90),
        ),
        2,
    )

    credit_conso = "Oui" if encours_conso > 500.0 else yn(rng, 0.04)
    credit_immo = "Oui" if encours_immo > 1_000.0 else yn(rng, 0.025)
    credit_autre = yn(rng, 0.12 if statut == "Actif" else 0.04)

    eligible_score = 0
    eligible_score += 2 if statut == "Actif" else 0
    eligible_score += 2 if validation_kyc == "Oui" else 0
    eligible_score += 1 if revenu_domicilie == "Oui" else 0
    eligible_score += 1 if montant_revenu >= 4_000 else 0
    eligible_score += 1 if dossier_complet == "Oui" else 0

    eligible_credit = (
        "Oui"
        if statut != "Rupture de relation"
        and eligible_score >= 5
        and rng.random() < 0.86
        else "Non"
    )

    # --------------------------------------------------------
    # Digital / activité temporelle
    # --------------------------------------------------------
    app_installed = yn(rng, 0.82 if canal == "Digital" else 0.58)
    premiere_connex = (
        yn(rng, 0.89 if statut == "Actif" else 0.48)
        if app_installed == "Oui"
        else "Non"
    )

    compte_mobile = yn(rng, 0.78 if app_installed == "Oui" else 0.20)
    compte_mobile_active = (
        yn(rng, 0.91 if statut == "Actif" else 0.30)
        if compte_mobile == "Oui"
        else "Non"
    )

    carte_virtuelle = yn(rng, 0.44 if app_installed == "Oui" else 0.08)
    carte_virtuelle_active = (
        yn(rng, 0.88 if statut == "Actif" else 0.35)
        if carte_virtuelle == "Oui"
        else "Non"
    )

    compte_mad_convertible = yn(rng, 0.17)
    compte_mad_convertible_active = (
        yn(rng, 0.84 if statut == "Actif" else 0.34)
        if compte_mad_convertible == "Oui"
        else "Non"
    )

    if statut == "Actif":
        is_actif_sem = yn(rng, 0.72)
        is_actif_mois = "Oui" if is_actif_sem == "Oui" else yn(rng, 0.68)
        is_actif_trois_mois = "Oui" if is_actif_mois == "Oui" else yn(rng, 0.60)
        is_actif_an = "Oui"
    else:
        is_actif_sem = yn(rng, 0.05)
        is_actif_mois = yn(rng, 0.10)
        is_actif_trois_mois = yn(rng, 0.16)
        is_actif_an = yn(rng, 0.28)

    is_inactif_sem = "Non" if is_actif_sem == "Oui" else "Oui"
    is_inactif_mois = "Non" if is_actif_mois == "Oui" else "Oui"
    is_inactif_trois_mois = "Non" if is_actif_trois_mois == "Oui" else "Oui"
    is_inactif_an = "Non" if is_actif_an == "Oui" else "Oui"

    # --------------------------------------------------------
    # Autres indicateurs catégoriels déjà présents dans le schéma
    # --------------------------------------------------------
    etudiant = "Oui" if age <= 27 and rng.random() < 0.45 else "Non"
    presence_maroc = yn(rng, 0.91)
    mdm = "Oui" if presence_maroc == "Non" and rng.random() < 0.58 else yn(rng, 0.07)
    bp = yn(rng, 0.13)

    carte_dispo_agence = (
        yn(rng, 0.70)
        if carte_actuelle != "Aucune" and activation_carte == "Non"
        else yn(rng, 0.08)
    )
    carte_retiree = (
        yn(rng, 0.90)
        if carte_actuelle != "Aucune" and activation_carte == "Oui"
        else yn(rng, 0.12)
    )

    chequier_dispo_agence = yn(rng, 0.16 if statut == "Actif" else 0.05)
    chequier_retire = (
        yn(rng, 0.77) if chequier_dispo_agence == "Oui" else yn(rng, 0.04)
    )
    chequier_active = (
        yn(rng, 0.88) if chequier_retire == "Oui" else "Non"
    )

    dotation_touristique = yn(rng, 0.24 if statut == "Actif" else 0.07)
    dotation_ecom = yn(rng, 0.43 if statut == "Actif" else 0.10)

    row = {
        "radical_compte": radical_compte,
        "Nom": nom,
        "Prenom": prenom,
        "ID_Client": id_client,
        "STATUT_CLIENT": statut,
        "Age": age,
        "Qualite": qualite,
        "Anciennete": anciennete,
        "Region": region,
        "Agence": agence,
        "Gestionnaire": gestionnaire,
        "Dossier_Complet": dossier_complet,
        "Validation_KYC": validation_kyc,
        "Activation_du_compte": activation_compte,
        "Activation_carte": activation_carte,
        "Canal_acquisition": canal,
        "Segment_actuel": segment,
        "Numero_Tel": numero_tel,
        "Mail": email,
        "Epargne": epargne,
        "Carte_Actuelle": carte_actuelle,
        "Assurance_Actuelle": assurance,
        "nb_transaction": nb_transaction,
        "vol_transaction": vol_transaction,
        "nb_retrait_gab": nb_retrait_gab,
        "vol_retrait_gab": vol_retrait_gab,
        "nb_transaction_ecom": nb_transaction_ecom,
        "vol_transaction_ecom": vol_transaction_ecom,
        "nb_virement": nb_virement,
        "vol_virement": vol_virement,
        "solde_moyen_depots": solde_moyen_depots,
        "encours_moyen": encours_moyen,
        "encours_global": encours_global,
        "encours_conso": encours_conso,
        "encours_immo": encours_immo,
        "revenu_domicilie": revenu_domicilie,
        "montant_revenu": montant_revenu,
        "App_instaled": app_installed,
        "Premiere_connex": premiere_connex,
        "carte_dispo_agence": carte_dispo_agence,
        "carte_retiree": carte_retiree,
        "Carte_virtuelle": carte_virtuelle,
        "Etudiant": etudiant,
        "Dotation_touristique": dotation_touristique,
        "Dotation_ecom": dotation_ecom,
        "Compte_CIH_Mobile": compte_mobile,
        "Compte_MAD_convertible": compte_mad_convertible,
        "MDM": mdm,
        "Presence_maroc": presence_maroc,
        "BP": bp,
        "chequier_dispo_agence": chequier_dispo_agence,
        "chequier_retire": chequier_retire,
        "chequier_active": chequier_active,
        "Nature_carte": nature_carte,
        "Categorie": categorie,
        "Nombre_transaction_inter": nombre_transaction_inter,
        "Volume_transaction_inter": volume_transaction_inter,
        "is_actif_sem": is_actif_sem,
        "is_actif_mois": is_actif_mois,
        "is_actif_trois_mois": is_actif_trois_mois,
        "is_actif_an": is_actif_an,
        "is_inactif_sem": is_inactif_sem,
        "is_inactif_mois": is_inactif_mois,
        "is_inactif_trois_mois": is_inactif_trois_mois,
        "is_inactif_an": is_inactif_an,
        "credit_conso": credit_conso,
        "credit_immo": credit_immo,
        "credit_autre": credit_autre,
        "Eligible_credit": eligible_credit,
        "Compte_CIH_Mobile_active": compte_mobile_active,
        "Compte_MAD_convertible_active": compte_mad_convertible_active,
        "Carte_virtuelle_active": carte_virtuelle_active,
        "Nb_Operation": nb_operation,
        "Vol_Operation": vol_operation,
    }

    return tuple(row[column] for column in COLUMNS)


def update_checksum(checksum: "hashlib._Hash", row: tuple[Any, ...]) -> None:
    # Format canonique indépendant du driver PostgreSQL.
    for value in row:
        if value is None:
            token = "<NULL>"
        elif isinstance(value, float):
            token = format(value, ".2f")
        else:
            token = str(value)
        checksum.update(token.encode("utf-8"))
        checksum.update(b"\x1f")
    checksum.update(b"\x1e")


def validate_schema(conn: psycopg.Connection[Any]) -> None:
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s
        """,
        (TABLE,),
    ).fetchall()

    actual = {str(row[0]) for row in rows}
    missing = [column for column in COLUMNS if column not in actual]

    if missing:
        raise RuntimeError(
            "Le schéma clients n'est pas compatible avec le seed. "
            f"Colonnes absentes: {', '.join(missing)}"
        )


def seed_clients(row_count: int, seed: int) -> str:
    load_environment()
    url = database_url()

    rng = random.Random(seed)

    # Important pour reproduire exactement noms/prénoms entre local et serveur.
    fake = Faker("fr_FR")
    fake.seed_instance(seed)

    checksum = hashlib.sha256()
    started_at = time.monotonic()

    with psycopg.connect(url) as conn:
        validate_schema(conn)

        # Accélère le chargement de test sans modifier la configuration globale
        # de PostgreSQL.
        conn.execute("SET LOCAL synchronous_commit = off")

        # Table temporaire de staging :
        # - aucune modification permanente du schéma
        # - permet un UPSERT massif et rejouable
        conn.execute(
            sql.SQL(
                "CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS) ON COMMIT DROP"
            ).format(
                sql.Identifier(STAGE_TABLE),
                sql.Identifier(TABLE),
            )
        )

        copy_stmt = sql.SQL("COPY {} ({}) FROM STDIN").format(
            sql.Identifier(STAGE_TABLE),
            sql.SQL(", ").join(sql.Identifier(c) for c in COLUMNS),
        )

        print(
            f"[seed] Génération de {row_count:,} clients "
            f"(seed={seed}) vers PostgreSQL..."
        )

        with conn.cursor() as cur:
            with cur.copy(copy_stmt) as copy:
                for i in range(1, row_count + 1):
                    row = build_client(i, rng, fake)
                    update_checksum(checksum, row)
                    copy.write_row(row)

                    if i % 50_000 == 0 or i == row_count:
                        elapsed = max(0.001, time.monotonic() - started_at)
                        rate = int(i / elapsed)
                        print(
                            f"[seed] {i:,}/{row_count:,} générés "
                            f"({rate:,} lignes/s)"
                        )

        print("[seed] Fusion des données dans clients...")

        update_columns = [c for c in COLUMNS if c != "radical_compte"]

        merge_stmt = sql.SQL(
            """
            INSERT INTO {target} ({columns})
            SELECT {columns}
            FROM {stage}
            ON CONFLICT ({pk}) DO UPDATE
            SET {updates}
            """
        ).format(
            target=sql.Identifier(TABLE),
            stage=sql.Identifier(STAGE_TABLE),
            pk=sql.Identifier("radical_compte"),
            columns=sql.SQL(", ").join(sql.Identifier(c) for c in COLUMNS),
            updates=sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(
                    sql.Identifier(c),
                    sql.Identifier(c),
                )
                for c in update_columns
            ),
        )

        conn.execute(merge_stmt)

        generated_count = conn.execute(
            sql.SQL(
                "SELECT COUNT(*) FROM {} WHERE {} LIKE %s"
            ).format(
                sql.Identifier(TABLE),
                sql.Identifier("radical_compte"),
            ),
            (f"{RADICAL_PREFIX}%",),
        ).fetchone()[0]

        conn.commit()

    elapsed = time.monotonic() - started_at
    digest = checksum.hexdigest()

    print()
    print("[OK] Seed terminé.")
    print(f"[OK] Lignes demandées : {row_count:,}")
    print(f"[OK] Lignes Faker présentes : {generated_count:,}")
    print(f"[OK] Seed : {seed}")
    print(f"[OK] SHA256 génération : {digest}")
    print(f"[OK] Durée : {elapsed:.1f}s")
    print()
    print(
        "Le SHA256 doit être identique en local et sur le serveur "
        "si le nombre de lignes, le seed et la version de Faker sont identiques."
    )

    return digest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Génère un dataset clients Faker déterministe et l'insère "
            "dans PostgreSQL."
        )
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=DEFAULT_ROWS,
        help=f"Nombre de clients à générer (défaut: {DEFAULT_ROWS}).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Seed déterministe (défaut: {DEFAULT_SEED}).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.rows <= 0:
        raise SystemExit("--rows doit être strictement positif.")

    seed_clients(args.rows, args.seed)


if __name__ == "__main__":
    main()
