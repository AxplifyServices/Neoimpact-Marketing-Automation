from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel

import pandas as pd
from app.storage import db

router = APIRouter()

# =========================================================
# CONFIG USE CASES — table clients uniquement
# =========================================================

USECASE_COLUMNS = {
    "formulaire-client": [
        "radical_compte", "Nom", "Prenom", "ID_Client",
        "Numero_Tel", "Mail",
        "Age", "Qualite",
        "Region", "Agence", "Gestionnaire",
        "STATUT_CLIENT",
        "Segment_actuel", "Canal_acquisition",
        "Epargne",
        "Carte_Actuelle", "Assurance_Actuelle",
        "Nature_carte", "Categorie",
    ],

    "cible": [
        "STATUT_CLIENT", "Segment_actuel", "Canal_acquisition",
        "Region", "Agence", "Gestionnaire",
        "Age", "Anciennete", "Qualite",
        "Epargne", "Carte_Actuelle", "Assurance_Actuelle",
        "revenu_domicilie", "montant_revenu",
        "encours_moyen", "encours_global", "encours_conso", "encours_immo",
        "solde_moyen_depots",
        "nb_transaction", "vol_transaction",
        "nb_retrait_gab", "vol_retrait_gab",
        "nb_transaction_ecom", "vol_transaction_ecom",
        "nb_virement", "vol_virement",
        "Nombre_transaction_inter", "Volume_transaction_inter",
        "Etudiant", "Presence_maroc", "MDM", "BP",
    ],

    "objectif": [
        "Dossier_Complet",
        "Validation_KYC",
        "Activation_du_compte",
        "Activation_carte",
        "App_instaled",
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
        "Compte_MAD_convertible",
    ],

    "condition": [
        "STATUT_CLIENT", "Segment_actuel", "Canal_acquisition",
        "Region", "Agence", "Gestionnaire",
        "Age", "Anciennete", "Qualite",
        "Epargne", "Carte_Actuelle", "Assurance_Actuelle",
        "revenu_domicilie", "montant_revenu",
        "encours_moyen", "encours_global", "encours_conso", "encours_immo",
        "solde_moyen_depots",
        "nb_transaction", "vol_transaction",
        "nb_retrait_gab", "vol_retrait_gab",
        "nb_transaction_ecom", "vol_transaction_ecom",
        "nb_virement", "vol_virement",
        "Nombre_transaction_inter", "Volume_transaction_inter",
        "Etudiant", "Presence_maroc", "MDM", "BP",
        "Nature_carte", "Categorie",
    ],
}


class ReadTableIn(BaseModel):
    table: str
    filters: Optional[Dict[str, Any]] = None  # format simple (numeric/categorical)
    limit: Optional[int] = 500
    offset: int = 0  # interprété comme "page_start"
    pages: Optional[int] = 1  # NEW: nombre de pages à charger



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
    """
    Heuristique simple SQLite:
      - TEXT/CHAR/VARCHAR/CLOB => catégoriel
      - sinon => numérique/temps/etc.
    """
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

import re
from typing import Any, Dict, List
from fastapi import Query

def _clients_schema() -> Dict[str, str]:
    return {str(c): str(t) for c, t in db.get_table_columns("clients")}

def _is_numeric_sql(sql_type: str) -> bool:
    t = (sql_type or "").upper()
    return any(k in t for k in ("INT", "REAL", "NUM", "DEC", "DOUBLE", "FLOAT"))

def _distinct_clients(col: str, limit: int = 5000):
    return db.get_distinct_values("clients", col, limit=limit)

def _is_free_text(values: List[Any], max_modalities: int = 200) -> bool:
    return len(values) > max_modalities

# Modalités négatives à exclure pour OBJECTIF
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

        if _is_numeric_sql(schema[col]):
            out[col] = "Numérique"
            continue

        vals = _distinct_clients(col, limit=limit)

        if _is_free_text(vals):
            out[col] = "Text"
            continue

        if positive_only:
            vals = _filter_positive(vals)

        out[col] = vals

    return out


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


# =========================================================
# NEW: list categorical columns
# =========================================================
@router.get("/data/tables/{table}/categorical-columns")
def categorical_columns(table: str):
    """
    Renvoie la liste des colonnes catégorielles (basé sur le type SQL).
    """
    cols = _get_categorical_columns(table)
    return {"table": table, "categorical_columns": cols, "count": len(cols)}


# =========================================================
# NEW: modalities for ALL categorical columns
# =========================================================
@router.get("/data/tables/{table}/categorical-modalities")
def categorical_modalities(
    table: str,
    limit: int = Query(default=250, ge=1, le=5000),
):
    """
    Renvoie toutes les modalités de chaque colonne catégorielle:
    {
      "table": "...",
      "limit": 250,
      "modalities": {
         "STATUT_CLIENT": ["Actif", "Inactif", ...],
         "Region": ["Casablanca", "Rabat", ...]
      }
    }
    """
    cols = _get_categorical_columns(table)
    modalities: Dict[str, List[Any]] = {}
    for c in cols:
        modalities[c] = db.get_distinct_values(table, c, limit=limit)
    return {"table": table, "limit": limit, "modalities": modalities}


@router.post("/data/read")
def read_table(payload: ReadTableIn):
    db_filters = _build_filters(payload.filters)

    # --- NEW: pagination par "pages" ---
    limit = int(payload.limit or 500)
    if limit <= 0:
        limit = 500

    pages = int(payload.pages or 1)
    if pages < 1:
        pages = 1
    if pages > 50:
        pages = 50  # garde-fou anti surcharge

    page_start = int(payload.offset or 0)  # on réutilise offset comme page_start
    if page_start < 0:
        page_start = 0

    row_offset = page_start * limit
    row_limit = limit * pages

    df = db.read_table(payload.table, filters=db_filters, limit=row_limit, offset=row_offset)

    # "offset" renvoyé = page_start, pas row_offset (plus clair pour le front)
    return {
        "table": payload.table,
        "rows": df.to_dict(orient="records"),
        "count": int(len(df)),
        "limit": limit,             # taille page
        "pages": pages,             # nb pages retournées
        "page_start": page_start,   # page de départ
        "row_offset": row_offset,   # offset réel en lignes
        "row_limit": row_limit,     # limite réelle en lignes
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
    return _build_meta(
        USECASE_COLUMNS["formulaire-client"],
        limit=limit,
        positive_only=False,
    )

@router.get("/meta/cible")
def meta_cible(limit: int = Query(default=5000, ge=1, le=50000)):
    return _build_meta(
        USECASE_COLUMNS["cible"],
        limit=limit,
        positive_only=False,
    )

@router.get("/meta/objectif")
def meta_objectif(limit: int = Query(default=5000, ge=1, le=50000)):
    return _build_meta(
        USECASE_COLUMNS["objectif"],
        limit=limit,
        positive_only=True,  # ⚠️ modalités positives uniquement
    )

@router.get("/meta/condition")
def meta_condition(limit: int = Query(default=5000, ge=1, le=50000)):
    return _build_meta(
        USECASE_COLUMNS["condition"],
        limit=limit,
        positive_only=False,
    )
