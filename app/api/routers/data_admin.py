from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter
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

@router.get("/data/tables")
def list_tables():
    return {"tables": db.list_tables()}

@router.get("/data/tables/{table}/columns")
def table_columns(table: str):
    cols = db.get_table_columns(table)
    return {"table": table, "columns": [{"name": c, "type": t} for c, t in cols]}

@router.get("/data/tables/{table}/distinct")
def distinct_values(table: str, col: str, limit: int = 250):
    return {"table": table, "col": col, "values": db.get_distinct_values(table, col, limit=limit)}

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
