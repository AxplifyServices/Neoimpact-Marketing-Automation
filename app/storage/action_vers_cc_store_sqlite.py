from __future__ import annotations

import os
import sqlite3
from datetime import date
from typing import Any, Dict, Optional

from app.storage.campagnes_store_sqlite import get_campagne
from app.storage.modele_store_sqlite import get_modele

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "clients.db")

TABLE_NAME = "action_vers_cc"

# Mapping variable_cible (libellé modèle) -> colonne clients.db
VARIABLE_CIBLE_TO_CLIENT_COL = {
    "STATUT_CLIENT": "STATUT_CLIENT",
    "Dossier Complet": "Dossier_Complet",
    "Validation KYC": "Validation_KYC",
    "Activation du compte": "Activation_du_compte",
    "Activation carte": "Activation_carte",
    "Epargne": "Epargne",
    "Carte Actuelle": "Carte_Actuelle",
    "Assurance Actuelle": "Assurance_Actuelle",
}


CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
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

    colonne          TEXT,   -- variable cible (libellé)
    objectif         TEXT,   -- objectif du modèle
    traitement       TEXT,   -- valeur courante (modifiable)

    PRIMARY KEY (id_campagne, radical_compte)
);
"""


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _today_iso() -> str:
    return date.today().isoformat()


def ensure_action_vers_cc_table() -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(CREATE_SQL)

    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_camp ON {TABLE_NAME}(id_campagne)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_rc ON {TABLE_NAME}(radical_compte)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_date ON {TABLE_NAME}(date_affectation)")

    conn.commit()
    conn.close()


def _get_client_row(radical_compte: str) -> Optional[Dict[str, Any]]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM clients WHERE radical_compte = ? LIMIT 1", (radical_compte,))
    r = cur.fetchone()
    conn.close()
    return dict(r) if r else None


def _get_current_traitement(client_row: Dict[str, Any], variable_cible_label: str) -> str:
    col = VARIABLE_CIBLE_TO_CLIENT_COL.get(variable_cible_label)
    if not col:
        return ""
    val = client_row.get(col)
    if val is None:
        return ""
    return str(val)


def insert_or_update_action_vers_cc(row: Dict[str, Any]) -> None:
    ensure_action_vers_cc_table()

    conn = _connect()
    cur = conn.cursor()

    sql = f"""
    INSERT INTO {TABLE_NAME} (
        radical_compte, id_campagne,
        date_affectation, nb_jour_affecte,
        nom, prenom, numero_tel, adresse_mail, region, agence, gestionnaire,
        colonne, objectif, traitement
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id_campagne, radical_compte) DO UPDATE SET
        date_affectation=excluded.date_affectation,
        nb_jour_affecte=excluded.nb_jour_affecte,
        nom=excluded.nom,
        prenom=excluded.prenom,
        numero_tel=excluded.numero_tel,
        adresse_mail=excluded.adresse_mail,
        region=excluded.region,
        agence=excluded.agence,
        gestionnaire=excluded.gestionnaire,
        colonne=excluded.colonne,
        objectif=excluded.objectif,
        traitement=excluded.traitement
    """

    cur.execute(
        sql,
        (
            row.get("radical_compte"),
            row.get("id_campagne"),
            row.get("date_affectation"),
            row.get("nb_jour_affecte"),
            row.get("nom"),
            row.get("prenom"),
            row.get("numero_tel"),
            row.get("adresse_mail"),
            row.get("region"),
            row.get("agence"),
            row.get("gestionnaire"),
            row.get("colonne"),
            row.get("objectif"),
            row.get("traitement"),
        ),
    )

    conn.commit()
    conn.close()


def create_action_vers_cc_from_campaign(id_campagne: str, radical_compte: str) -> Dict[str, Any]:
    """
    Construit + upsert une ligne action_vers_cc en récupérant :
    - infos client depuis table clients
    - variable cible / objectif depuis modèle lié à la campagne
    - traitement = valeur courante de la colonne cible dans clients
    """
    ensure_action_vers_cc_table()

    camp = get_campagne(id_campagne)
    if not camp:
        raise ValueError(f"Campagne introuvable: {id_campagne}")

    id_modele = str(camp.get("id_modele", "") or "").strip()
    if not id_modele:
        raise ValueError(f"Campagne {id_campagne}: id_modele vide")

    modele = get_modele(id_modele)
    if not modele:
        raise ValueError(f"Modèle introuvable: {id_modele}")

    variable_cible = str(modele.get("variable_cible", "") or "").strip()
    objectif = str(modele.get("Objectif", "") or "").strip()

    client = _get_client_row(radical_compte)
    if not client:
        raise ValueError(f"Client introuvable: radical_compte={radical_compte}")

    row = {
        "radical_compte": radical_compte,
        "id_campagne": id_campagne,
        "date_affectation": _today_iso(),
        "nb_jour_affecte": 0,
        "nom": client.get("Nom", ""),
        "prenom": client.get("Prenom", ""),
        "numero_tel": client.get("Numero_Tel", ""),
        "adresse_mail": client.get("Mail", ""),
        "region": client.get("Region", ""),
        "agence": client.get("Agence", ""),
        "gestionnaire": client.get("Gestionnaire", ""),
        "colonne": variable_cible,
        "objectif": objectif,
        "traitement": _get_current_traitement(client, variable_cible),
    }

    insert_or_update_action_vers_cc(row)
    return row
