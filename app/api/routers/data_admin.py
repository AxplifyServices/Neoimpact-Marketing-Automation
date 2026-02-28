from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel

import pandas as pd
from app.storage import db

router = APIRouter()

# =========================================================
# CONFIG USE CASES — table clients uniquement
# (inchangé: même répartition formulaire/cible/objectif/condition)
# =========================================================
USECASE_COLUMNS = {
    "formulaire-client": [
        "Nom", "Prenom", "ID_Client",
        "Numero_Tel", "Mail",
        "Age", "Qualite",
        "Region", "Agence", "Gestionnaire",
        "STATUT_CLIENT",
        "Segment_actuel", "Canal_acquisition",
        "Epargne",
        "Carte_Actuelle", "Assurance_Actuelle",
        "Nature_carte", "Categorie", "Dossier_Complet", "Validation_KYC", "Activation_du_compte",
        "Activation_carte", "nb_transaction", "vol_transaction",
        "nb_retrait_gab", "vol_retrait_gab", "nb_transaction_ecom", "vol_transaction_ecom",
        "nb_virement", "vol_virement", "solde_moyen_depots", "encours_moyen", "encours_global", "encours_conso", "encours_immo",
        "revenu_domicilie", "montant_revenu", "App_instaled",
        "Premiere_connex",
        "carte_dispo_agence",
        "carte_retiree",
        "Carte_virtuelle",
        "chequier_dispo_agence",
        "chequier_retire",
        "chequier_active",
        "Dotation_touristique",
        "Dotation_ecom",
        "Compte_CIH_Mobile",
        "Compte_MAD_convertible", "Etudiant", "Presence_maroc", "MDM", "BP", "Nature_carte", "Categorie",
        "chequier_dispo_agence",
        "chequier_retire",
        "chequier_active",
          "is_actif_sem",
"is_actif_mois",
"is_actif_trois_mois",
"is_actif_an",

"is_inactif_sem",
"is_inactif_mois",
"is_inactif_trois_mois",
"is_inactif_an" ,

"credit_conso" ,
"credit_immo" ,
"credit_autre" ,

"Eligible_credit" ,

"Compte CIH Mobile active" ,

"Compte MAD convertible" ,

"Compte MAD convertible active" ,

"Carte viertuelle active" ,

"Nb Operation" ,
"Vol Operation" ,
    ],

    "cible": [
        "Age", "Qualite",
        "Region", "Agence", "Gestionnaire",
        "STATUT_CLIENT",
        "Segment_actuel", "Canal_acquisition",
        "Epargne",
        "Carte_Actuelle", "Assurance_Actuelle",
        "Nature_carte", "Categorie", "Dossier_Complet", "Validation_KYC", "Activation_du_compte",
        "Activation_carte", "nb_transaction", "vol_transaction",
        "nb_retrait_gab", "vol_retrait_gab", "nb_transaction_ecom", "vol_transaction_ecom",
        "nb_virement", "vol_virement", "solde_moyen_depots", "encours_moyen", "encours_global", "encours_conso", "encours_immo",
        "revenu_domicilie", "montant_revenu", "App_instaled",
        "Premiere_connex",
        "carte_dispo_agence",
        "carte_retiree",
        "Carte_virtuelle",
        "chequier_dispo_agence",
        "chequier_retire",
        "chequier_active",
        "Dotation_touristique",
        "Dotation_ecom",
        "Compte_CIH_Mobile",
        "Compte_MAD_convertible", "Etudiant", "Presence_maroc", "MDM", "BP", "Nature_carte", "Categorie",
        "chequier_dispo_agence",
        "chequier_retire",
        "chequier_active",
        "is_actif_mois",
"is_actif_trois_mois",
"is_actif_an",

"is_inactif_sem",
"is_inactif_mois",
"is_inactif_trois_mois",
"is_inactif_an" ,

"credit_conso" ,
"credit_immo" ,
"credit_autre" ,

"Eligible_credit" ,

"Compte CIH Mobile active" ,

"Compte MAD convertible" ,

"Compte MAD convertible active" ,

"Carte viertuelle active" ,

"Nb Operation" ,
"Vol Operation" ,
    ],

    "objectif": [
        "STATUT_CLIENT",
        "Segment_actuel",
        "Epargne",
        "Carte_Actuelle", "Assurance_Actuelle",
        "Nature_carte", "Categorie", "Dossier_Complet", "Validation_KYC", "Activation_du_compte",
        "Activation_carte", "nb_transaction", "vol_transaction",
        "nb_retrait_gab", "vol_retrait_gab", "nb_transaction_ecom", "vol_transaction_ecom",
        "nb_virement", "vol_virement", "solde_moyen_depots", "encours_moyen", "encours_global", "encours_conso", "encours_immo",
        "revenu_domicilie", "montant_revenu", "App_instaled",
        "Premiere_connex",
        "carte_dispo_agence",
        "carte_retiree",
        "Carte_virtuelle",
        "chequier_dispo_agence",
        "chequier_retire",
        "chequier_active",
        "Dotation_touristique",
        "Dotation_ecom",
        "Compte_CIH_Mobile",
        "Compte_MAD_convertible", "Nature_carte",
        "chequier_dispo_agence",
        "chequier_retire",
        "chequier_active", "Presence_maroc", "is_actif_mois",
"is_actif_trois_mois",
"is_actif_an",

"is_inactif_sem",
"is_inactif_mois",
"is_inactif_trois_mois",
"is_inactif_an" ,

"credit_conso" ,
"credit_immo" ,
"credit_autre" ,

"Eligible_credit" ,

"Compte CIH Mobile active" ,

"Compte MAD convertible" ,

"Compte MAD convertible active" ,

"Carte viertuelle active" ,

"Nb Operation" ,
"Vol Operation" ,
    ],

    "condition": [
        "STATUT_CLIENT",
        "Segment_actuel",
        "Epargne",
        "Carte_Actuelle", "Assurance_Actuelle",
        "Nature_carte", "Categorie", "Dossier_Complet", "Validation_KYC", "Activation_du_compte",
        "Activation_carte", "nb_transaction", "vol_transaction",
        "nb_retrait_gab", "vol_retrait_gab", "nb_transaction_ecom", "vol_transaction_ecom",
        "nb_virement", "vol_virement", "solde_moyen_depots", "encours_moyen", "encours_global", "encours_conso", "encours_immo",
        "revenu_domicilie", "montant_revenu", "App_instaled",
        "Premiere_connex",
        "carte_dispo_agence",
        "carte_retiree",
        "Carte_virtuelle",
        "chequier_dispo_agence",
        "chequier_retire",
        "chequier_active",
        "Dotation_touristique",
        "Dotation_ecom",
        "Compte_CIH_Mobile",
        "Compte_MAD_convertible", "Nature_carte",
        "chequier_dispo_agence",
        "chequier_retire",
        "chequier_active", "Presence_maroc", 
        "is_actif_mois",
"is_actif_trois_mois",
"is_actif_an",

"is_inactif_sem",
"is_inactif_mois",
"is_inactif_trois_mois",
"is_inactif_an" ,

"credit_conso" ,
"credit_immo" ,
"credit_autre" ,

"Eligible_credit" ,

"Compte CIH Mobile active" ,

"Compte MAD convertible" ,

"Compte MAD convertible active" ,

"Carte viertuelle active" ,

"Nb Operation" ,
"Vol Operation" ,
    ],
}

# =========================================================
# NEW: Hardcoded mapping (clients)
# - Colonnes listées ici => modalités hardcodées
# - Colonnes non listées => restent extractibles depuis la DB (distinct)
# =========================================================

YES_NO = ["Oui", "Non"]

# Colonnes que tu veux FORCER en "Numérique" (même si le type SQL est mal déclaré)
FORCE_NUMERIC = {
    "Nb Operation",
    "Vol Operation",
    "Nb_Operation",
    "Vol_Operation",
}

# Mapping catégoriel hardcodé
CATEGORICAL_MAPPING: Dict[str, List[str]] = {
    # --- Nouvelles colonnes Oui/Non ---
    "is_actif_sem": YES_NO,
    "is_actif_mois": YES_NO,
    "is_actif_trois_mois": YES_NO,
    "is_actif_an": YES_NO,

    "is_inactif_sem": YES_NO,
    "is_inactif_mois": YES_NO,
    "is_inactif_trois_mois": YES_NO,
    "is_inactif_an": YES_NO,

    "credit_conso": YES_NO,
    "credit_immo": YES_NO,
    "credit_autre": YES_NO,

    "Eligible_credit": YES_NO,

    # Attention: je mets des variantes probables (underscore) pour éviter mismatch
    "Compte_CIH_Mobile_active": YES_NO,
    "Compte CIH Mobile active": YES_NO,

    "Compte_MAD_convertible": YES_NO,  # déjà existant, on fixe aussi ici
    "Compte MAD convertible": YES_NO,

    "Compte_MAD_convertible_active": YES_NO,
    "Compte MAD convertible active": YES_NO,

    "Carte_virtuelle_active": YES_NO,
    "Carte viertuelle active": YES_NO,  # tel que fourni (typo "viertuelle")

    # --- Colonnes à modifier ---
    "Epargne": YES_NO,

    "Segment_actuel": [
        "Affluent", "En stress", "Jeunes", "Mass Market", "Premium", "Medium", "Haut de gamme"
    ],
    "Segment Actuel": [
        "Affluent", "En stress", "Jeunes", "Mass Market", "Premium", "Medium", "Haut de gamme"
    ],

    # Assurance_Actuelle (existant) -> mapping demandé
    "Assurance_Actuelle": ["Aucune", "Immobilier", "Vie"],
    "Assurance": ["Aucune", "Immobilier", "Vie"],

    "Nature_carte": ["CMI", "MasterCard", "Visa", "Aucune"],
    "Nature Carte": ["CMI", "MasterCard", "Visa", "Aucune"],

    "Dossier_Complet": YES_NO,
    "Dossier Complet": YES_NO,

    "Validation_KYC": YES_NO,
    "Validation KYC": YES_NO,

    "Activation_du_compte": YES_NO,
    "Activation Du Compte": YES_NO,

    "Activation_carte": YES_NO,
    "Activation Carte": YES_NO,

    "Compte_CIH_Mobile": YES_NO,
    "Compte CIH Mobile": YES_NO,

    "Qualite": ["Femme", "Homme"],
    "Canal_acquisition": ["Agence", "Digital"],
    "Canal Acquisition": ["Agence", "Digital"],

    # --- Mapping de l'existant (hardcodé) ---
    "STATUT_CLIENT": ["Actif", "Inactif", "Prospect", "Rupture de relation"],

    "Carte_Actuelle": ["Aucune", "Black", "Classic", "Code 212", "Code 30", "Gold", "Silver", "Standard"],

    "Categorie": ["Entreprise", "Particulier", "Pro/TPE"],

    "revenu_domicilie": YES_NO,
    "Revenu Domicilie": YES_NO,

    "App_instaled": YES_NO,
    "App Instaled": YES_NO,

    "Premiere_connex": YES_NO,
    "Premiere Connex": YES_NO,

    "carte_dispo_agence": YES_NO,
    "Carte Dispo Agence": YES_NO,

    "carte_retiree": YES_NO,
    "Carte Retiree": YES_NO,

    "Carte_virtuelle": YES_NO,
    "Carte Virtuelle": YES_NO,

    "chequier_dispo_agence": YES_NO,
    "Chequier Dispo Agence": YES_NO,

    "chequier_retire": YES_NO,
    "Chequier Retire": YES_NO,

    "chequier_active": YES_NO,
    "Chequier Active": YES_NO,

    "Dotation_touristique": YES_NO,
    "Dotation Touristique": YES_NO,

    "Dotation_ecom": YES_NO,
    "Dotation Ecom": YES_NO,
}

# =========================================================
# API Models
# =========================================================
class ReadTableIn(BaseModel):
    table: str
    filters: Optional[Dict[str, Any]] = None
    limit: Optional[int] = 500
    offset: int = 0
    pages: Optional[int] = 1


class UpdateCellIn(BaseModel):
    table: str
    rowid: int
    col: str
    value: Any


def _build_filters(filters: Optional[Dict[str, Any]]) -> Optional[Dict[str, db.ColumnFilter]]:
    if not filters:
        return None
    out: Dict[str, db.ColumnFilter] = {}
    for col, f in filters.items():
        if not isinstance(f, dict):
            continue
        if "numeric" in f:
            nb = f["numeric"] or {}
            out[col] = db.ColumnFilter(numeric=db.NumericBounds(min=nb.get("min"), max=nb.get("max")))
        elif "categorical" in f:
            out[col] = db.ColumnFilter(categorical=[str(x) for x in (f["categorical"] or [])])
    return out


# -----------------------------
# NEW: categorical detection
# -----------------------------
def _is_categorical_sql_type(sql_type: str) -> bool:
    t = (sql_type or "").strip().lower()
    if not t:
        return False
    return any(k in t for k in ("text", "char", "varchar", "clob", "string"))


def _get_categorical_columns(table: str) -> List[str]:
    cols = db.get_table_columns(table)  # [(name, type), ...]
    out: List[str] = []
    for name, typ in cols:
        if _is_categorical_sql_type(str(typ)):
            out.append(str(name))
    return out


# =========================================================
# META helpers (clients uniquement)
# =========================================================
import re

def _clients_schema() -> Dict[str, str]:
    return {str(c): str(t) for c, t in db.get_table_columns("clients")}

def _is_numeric_sql(sql_type: str) -> bool:
    t = (sql_type or "").upper()
    return any(k in t for k in ("INT", "REAL", "NUM", "DEC", "DOUBLE", "FLOAT"))

def _distinct_clients(col: str, limit: int = 5000) -> List[Any]:
    """
    NEW:
    - Si la colonne est dans CATEGORICAL_MAPPING => retourne le mapping hardcodé
    - Sinon => distinct depuis la DB (comme avant)
    """
    if col in CATEGORICAL_MAPPING:
        return CATEGORICAL_MAPPING[col][:limit]

    # petites tentatives "best effort" si le front/DB utilisent variantes
    alt = col.replace(" ", "_")
    if alt in CATEGORICAL_MAPPING:
        return CATEGORICAL_MAPPING[alt][:limit]

    # fallback DB
    return db.get_distinct_values("clients", col, limit=limit)

def _is_free_text(values: List[Any], max_modalities: int = 200) -> bool:
    return len(values) > max_modalities

_NEG_PATTERNS = [
    r"\bnon\b", r"inactif", r"annul", r"echec", r"échec", r"refus",
    r"\bko\b", r"false", r"\b0\b", r"\bno\b",
]

def _filter_positive(vals: List[Any]) -> List[Any]:
    kept = []
    for v in vals:
        s = str(v).strip().lower()
        if not s or s in ("none", "null"):
            continue
        if any(re.search(p, s) for p in _NEG_PATTERNS):
            continue
        kept.append(v)
    return kept

def _build_meta(cols: List[str], limit: int, positive_only: bool) -> Dict[str, Any]:
    schema = _clients_schema()
    out: Dict[str, Any] = {}

    for col in cols:
        if col not in schema:
            continue  # colonne absente de clients

        # NEW: numeric override
        if col in FORCE_NUMERIC or col.replace(" ", "_") in FORCE_NUMERIC:
            out[col] = "Numérique"
            continue

        # numeric by SQL
        if _is_numeric_sql(schema[col]):
            out[col] = "Numérique"
            continue

        # NEW: mapping hardcodé si dispo, sinon DB distinct
        vals = _distinct_clients(col, limit=limit)

        if _is_free_text(vals):
            out[col] = "Text"
            continue

        if positive_only:
            vals = _filter_positive(vals)

        out[col] = vals

    return out


# =========================================================
# DATA APIs
# =========================================================
@router.get("/data/tables")
def list_tables():
    return {"tables": db.list_tables()}

@router.get("/data/tables/{table}/columns")
def table_columns(table: str):
    cols = db.get_table_columns(table)
    return {"table": table, "columns": [{"name": c, "type": t} for c, t in cols]}

@router.get("/data/tables/{table}/distinct")
def distinct_values(table: str, col: str, limit: int = 250):
    # endpoint existant (compat)
    return {"table": table, "col": col, "values": db.get_distinct_values(table, col, limit=limit)}

@router.get("/data/tables/{table}/categorical-columns")
def categorical_columns(table: str):
    cols = _get_categorical_columns(table)
    return {"table": table, "categorical_columns": cols, "count": len(cols)}

@router.get("/data/tables/{table}/categorical-modalities")
def categorical_modalities(
    table: str,
    limit: int = Query(default=250, ge=1, le=5000),
):
    """
    NEW:
    - Si table == clients => mapping hardcodé prioritaire par colonne
    - Sinon => DB distinct (comme avant)
    """
    cols = _get_categorical_columns(table)
    modalities: Dict[str, List[Any]] = {}

    for c in cols:
        if table == "clients":
            if c in CATEGORICAL_MAPPING:
                modalities[c] = CATEGORICAL_MAPPING[c][:limit]
                continue
            alt = c.replace(" ", "_")
            if alt in CATEGORICAL_MAPPING:
                modalities[c] = CATEGORICAL_MAPPING[alt][:limit]
                continue

        modalities[c] = db.get_distinct_values(table, c, limit=limit)

    return {"table": table, "limit": limit, "modalities": modalities}

@router.post("/data/read")
def read_table(payload: ReadTableIn):
    db_filters = _build_filters(payload.filters)

    limit = int(payload.limit or 500)
    if limit <= 0:
        limit = 500

    pages = int(payload.pages or 1)
    if pages < 1:
        pages = 1
    if pages > 50:
        pages = 50

    page_start = int(payload.offset or 0)
    if page_start < 0:
        page_start = 0

    row_offset = page_start * limit
    row_limit = limit * pages

    df = db.read_table(payload.table, filters=db_filters, limit=row_limit, offset=row_offset)

    return {
        "table": payload.table,
        "rows": df.to_dict(orient="records"),
        "count": int(len(df)),
        "limit": limit,
        "pages": pages,
        "page_start": page_start,
        "row_offset": row_offset,
        "row_limit": row_limit,
        "next_page_start": page_start + pages if len(df) == row_limit else None,
    }

@router.post("/data/update-cell")
def update_cell(payload: UpdateCellIn):
    db.update_cell(payload.table, payload.rowid, payload.col, payload.value)
    return {"ok": True}

# =========================================================
# META APIs — table clients uniquement
# =========================================================
@router.get("/meta/formulaire-client")
def meta_formulaire_client(limit: int = Query(default=5000, ge=1, le=50000)):
    return _build_meta(USECASE_COLUMNS["formulaire-client"], limit=limit, positive_only=False)

@router.get("/meta/cible")
def meta_cible(limit: int = Query(default=5000, ge=1, le=50000)):
    return _build_meta(USECASE_COLUMNS["cible"], limit=limit, positive_only=False)

@router.get("/meta/objectif")
def meta_objectif(limit: int = Query(default=5000, ge=1, le=50000)):
    return _build_meta(USECASE_COLUMNS["objectif"], limit=limit, positive_only=True)

@router.get("/meta/condition")
def meta_condition(limit: int = Query(default=5000, ge=1, le=50000)):
    return _build_meta(USECASE_COLUMNS["condition"], limit=limit, positive_only=False)