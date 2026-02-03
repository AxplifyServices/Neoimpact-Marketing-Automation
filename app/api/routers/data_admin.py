from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel

import pandas as pd
from app.storage import db

router = APIRouter()


class ReadTableIn(BaseModel):
    table: str
    filters: Optional[Dict[str, Any]] = None  # format simple (numeric/categorical)
    limit: Optional[int] = 500
    offset: int = 0


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
    df = db.read_table(payload.table, filters=db_filters, limit=payload.limit, offset=payload.offset)
    return {
        "table": payload.table,
        "rows": df.to_dict(orient="records"),
        "count": int(len(df)),
        "limit": payload.limit,
        "offset": payload.offset,
    }


@router.post("/data/update-cell")
def update_cell(payload: UpdateCellIn):
    db.update_cell(payload.table, payload.rowid, payload.col, payload.value)
    return {"ok": True}
