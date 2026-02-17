from __future__ import annotations

from typing import Any, Dict, Optional, List

import math
import numpy as np
import pandas as pd

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from pydantic import BaseModel
from fastapi.encoders import jsonable_encoder

from app.domain.ui_facades.cibles_ui_facade import (
    list_cibles_for_ui,
    get_cible_for_ui,
    get_locked_cibles_for_ui,
    get_distinct_values_for_ui,
    create_cible_db_for_ui,
    create_cible_file_for_ui,
    update_cible_for_ui,
    delete_cible_for_ui,
    preview_cible_for_ui,
    save_uploaded_file_for_ui,
    import_leads_into_clients_for_ui,
    get_cible_filtre_dict_for_ui,
)

router = APIRouter()

# Colonnes indispensables (STRICT) — alignées DB
STRICT_REQUIRED_COLS = ["ID_Client", "Numero_Tel", "Mail"]


# =========================================================
# Helpers: erreurs 400 structurées (schema strict)
# =========================================================
def _parse_strict_schema_error(err: Exception) -> Dict[str, Any]:
    raw = str(err).strip()
    lines = [l.strip() for l in raw.splitlines() if l.strip()]

    missing: List[str] = []
    extra: List[str] = []

    for line in lines:
        low = line.lower()

        # Colonnes manquantes
        if low.startswith("colonnes manquantes"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                missing = [c.strip() for c in parts[1].split(",") if c.strip()]

        # Colonnes en trop
        if low.startswith("colonnes en trop"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                extra = [c.strip() for c in parts[1].split(",") if c.strip()]

    message = lines[0] if lines else raw

    detail: Dict[str, Any] = {
        "error": "IMPORT_CLIENTS_STRICT_FAILED",
        "message": message,
        "required_columns": STRICT_REQUIRED_COLS,
        "missing_columns": missing,
        "extra_columns": extra,
        "raw": raw,
        "hint": "Le fichier doit correspondre EXACTEMENT au schéma de la table clients (noms + colonnes).",
    }
    return detail


def _raise_400_import_clients(e: Exception) -> None:
    detail = _parse_strict_schema_error(e)
    raise HTTPException(status_code=400, detail=detail)


# =========================================================
# Models
# =========================================================
class CibleDbCreateIn(BaseModel):
    nom_cible: str
    filtre: Dict[str, Any]


class CibleUpdateIn(BaseModel):
    id_cible: str
    nom_cible: str
    source: str
    date_creation: str
    filtre: Optional[Dict[str, Any]] = None
    chemin: str = ""


# =========================================================
# Routes
# =========================================================
@router.get("/cibles")
def list_cibles(
    limit: int = Query(default=200, ge=1, le=5000),  # taille page
    offset: int = Query(default=0, ge=0),            # page_start
    pages: Optional[int] = Query(default=None, ge=1, le=50),  # opt-in pagination
):
    """
    Ajoute locked + lock_reason pour l'UI.

    Pagination (opt-in):
      - si `pages` est fourni => renvoie un objet {items,total,...}
      - sinon => renvoie la LISTE comme avant (compat front)
    """
    cibles = list_cibles_for_ui() or []

    locked_ids, reasons = get_locked_cibles_for_ui()
    locked_ids = set(locked_ids or [])
    reasons = reasons or {}

    for c in cibles:
        if isinstance(c, dict):
            cid = c.get("id_cible") or c.get("id") or c.get("ID")
            is_locked = bool(cid in locked_ids)
            c["locked"] = is_locked
            c["lock_reason"] = (reasons.get(str(cid)) or reasons.get(cid)) if is_locked else None
        else:
            cid = getattr(c, "id_cible", None) or getattr(c, "id", None) or getattr(c, "ID", None)
            is_locked = bool(cid in locked_ids)
            try:
                setattr(c, "locked", is_locked)
                setattr(c, "lock_reason", (reasons.get(str(cid)) or reasons.get(cid)) if is_locked else None)
            except Exception:
                pass

    # --- compat: si pages n'est pas fourni, on renvoie EXACTEMENT comme avant ---
    if pages is None:
        return cibles

    # --- pagination "pages" ---
    page_start = int(offset or 0)
    per_page = int(limit or 200)
    nb_pages = int(pages or 1)

    start = page_start * per_page
    end = start + (per_page * nb_pages)

    items = cibles[start:end]

    return {
        "items": items,
        "count": int(len(items)),
        "total": int(len(cibles)),
        "limit": per_page,
        "pages": nb_pages,
        "page_start": page_start,
        "next_page_start": page_start + nb_pages if end < len(cibles) else None,
    }


@router.get("/cibles/{id_cible}")
def get_cible(id_cible: str):
    return get_cible_for_ui(id_cible)


@router.get("/cibles/{id_cible}/filtre")
def get_cible_filtre(id_cible: str):
    row = get_cible_for_ui(id_cible)
    if not row:
        return {"filtre": {}}
    return {"filtre": get_cible_filtre_dict_for_ui(row)}


@router.get("/cibles/locked")
def locked_cibles():
    locked_ids, reasons = get_locked_cibles_for_ui()
    return {"locked_ids": sorted(list(locked_ids or [])), "reasons": reasons or {}}


@router.post("/cibles/db")
def create_cible_db(payload: CibleDbCreateIn):
    new_id = create_cible_db_for_ui(payload.nom_cible, payload.filtre)
    return {"ok": True, "id_cible": new_id}


@router.post("/cibles/file")
async def create_cible_file(
    nom_cible: str = Form(...),
    file: UploadFile = File(...),
):
    """
    ✅ Auto-update clients puis création de cible fichier plat.
    - upload fichier
    - import/upsert clients automatiquement (STRICT)
    - création cible fichier plat ensuite
    """
    try:
        path = save_uploaded_file_for_ui(file)
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "UPLOAD_FAILED", "message": str(e)})

    # 1) auto import/upsert clients
    try:
        inserted, updated = import_leads_into_clients_for_ui(path)
    except Exception as e:
        _raise_400_import_clients(e)

    # 2) create cible file
    try:
        new_id = create_cible_file_for_ui(nom_cible, path)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "CREATE_CIBLE_FAILED", "message": str(e)})

    return {
        "ok": True,
        "id_cible": new_id,
        "file_path": path,
        "clients_inserted": inserted,
        "clients_updated": updated,
    }


@router.put("/cibles/{id_cible}")
def update_cible(id_cible: str, payload: CibleUpdateIn):
    update_cible_for_ui(
        id_cible=id_cible,
        nom_cible=payload.nom_cible,
        source=payload.source,
        date_creation=payload.date_creation,
        filtre_dict=payload.filtre,
        chemin=payload.chemin,
    )
    return {"ok": True}


@router.delete("/cibles/{id_cible}")
def delete_cible(id_cible: str):
    id_cible = (id_cible or "").strip()

    locked_ids, reasons = get_locked_cibles_for_ui()
    locked_ids = set(str(x).strip() for x in (locked_ids or []))
    reasons = reasons or {}

    if id_cible in locked_ids:
        reason = reasons.get(id_cible) or reasons.get(str(id_cible))
        msg = "Suppression impossible : cette cible est liée à une campagne active/planifiée."
        if reason:
            msg += f" ({reason})"
        raise HTTPException(status_code=409, detail=msg)

    delete_cible_for_ui(id_cible)
    return {"ok": True}


@router.get("/cibles/{id_cible}/preview")
def preview_cible(id_cible: str, limit: int = 200):
    """
    Preview JSON-safe:
    - remplace NaN/Inf par None (JSON strict)
    - convertit numpy scalars -> types python
    - datetime -> ISO string
    """
    df_head, total = preview_cible_for_ui(id_cible, limit=limit)

    if df_head is None:
        return {"total": int(total or 0), "rows": []}

    df2 = df_head.copy()

    # Force object + NaN/NaT -> None
    df2 = df2.astype(object).where(pd.notna(df2), None)

    # Datetime -> ISO string
    for col in df2.columns:
        try:
            if pd.api.types.is_datetime64_any_dtype(df_head[col]):
                df2[col] = pd.to_datetime(df_head[col]).dt.strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            pass

    rows = df2.to_dict(orient="records")

    # Nettoyage récursif JSON strict
    def _clean_json(x):
        if x is None:
            return None
        if isinstance(x, (np.integer,)):
            return int(x)
        if isinstance(x, (np.floating,)):
            v = float(x)
            return None if (math.isnan(v) or math.isinf(v)) else v
        if isinstance(x, float):
            return None if (math.isnan(x) or math.isinf(x)) else x
        if isinstance(x, dict):
            return {k: _clean_json(v) for k, v in x.items()}
        if isinstance(x, list):
            return [_clean_json(v) for v in x]
        return x

    rows = _clean_json(rows)

    return {"total": int(total or 0), "rows": jsonable_encoder(rows)}


@router.get("/clients/distinct")
def clients_distinct(column: str):
    return {"column": column, "values": get_distinct_values_for_ui(column)}


@router.post("/clients/import-leads")
async def import_leads(file: UploadFile = File(...)):
    """
    Retourne inserted + updated.
    """
    try:
        path = save_uploaded_file_for_ui(file)
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "UPLOAD_FAILED", "message": str(e)})

    try:
        inserted, updated = import_leads_into_clients_for_ui(path)
    except Exception as e:
        _raise_400_import_clients(e)

    return {"ok": True, "inserted": inserted, "updated": updated, "skipped": 0, "file_path": path}
