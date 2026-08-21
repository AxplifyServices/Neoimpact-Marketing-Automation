from __future__ import annotations

from typing import Any, Dict, Optional, List

import math
import numpy as np
import pandas as pd

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from pydantic import BaseModel
from app.storage.postgres_db import connection
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
    list_campaigns_for_objective_filter_ui,
)

router = APIRouter()

# Colonnes indispensables (STRICT) — alignées DB
STRICT_REQUIRED_COLS = ["ID_Client", "Numero_Tel", "Mail"]

SEGMENT_VALUES = {
    "Mass Market",
    "Medium",
    "Haut de gamme",
    "Premium",
    "Banque privée",
}


def _validate_segment_filter(filtre: Optional[Dict[str, Any]]) -> None:
    if not filtre or "Segment_actuel" not in filtre:
        return

    raw = filtre.get("Segment_actuel")
    if isinstance(raw, dict):
        raw = raw.get("values")

    if not isinstance(raw, list):
        raise HTTPException(
            status_code=400,
            detail="Le filtre Segment_actuel doit contenir une liste de segments.",
        )

    invalid = sorted({str(value) for value in raw if str(value) not in SEGMENT_VALUES})
    if invalid:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_SEGMENT_FILTER",
                "message": "Certaines valeurs de segmentation ne sont plus disponibles.",
                "invalid_values": invalid,
                "allowed_values": sorted(SEGMENT_VALUES),
            },
        )


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
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    pages: Optional[int] = Query(default=None, ge=1, le=50),
    q: Optional[str] = Query(default=None, max_length=200),
    source: Optional[str] = Query(default=None, max_length=20),
    locked: Optional[bool] = Query(default=None),
    date_min: Optional[str] = Query(default=None, max_length=32),
    date_max: Optional[str] = Query(default=None, max_length=32),
    objectif_mode: Optional[str] = Query(default=None, pattern='^(atteint|non_atteint|none)$'),
    objectif_campaign: Optional[str] = Query(default=None, max_length=100),
    sort_by: Optional[str] = Query(default=None, max_length=50),
    sort_dir: str = Query(default='desc', pattern='^(asc|desc)$'),
):
    """Liste des cibles avec vraie pagination/recherche SQL.

    La compatibilité historique est conservée lorsque ``pages`` n'est pas
    fourni. L'écran React utilise ``pages=1`` et ne matérialise donc plus
    toutes les cibles avant de découper une page en Python.
    """
    if pages is None and not any((q, source, locked is not None, date_min, date_max, objectif_mode, objectif_campaign)):
        # Compatibilité des anciens consommateurs internes/Streamlit.
        cibles = list_cibles_for_ui() or []
        locked_ids, reasons = get_locked_cibles_for_ui()
        locked_ids = set(locked_ids or [])
        reasons = reasons or {}
        for cible in cibles:
            if not isinstance(cible, dict):
                continue
            cid = str(cible.get("id_cible") or "").strip()
            cible["locked"] = cid in locked_ids
            cible["lock_reason"] = reasons.get(cid) if cid in locked_ids else None
        return cibles

    page_start = int(offset or 0)
    per_page = int(limit or 200)
    nb_pages = int(pages or 1)
    row_limit = per_page * nb_pages
    row_offset = page_start * per_page

    where_parts: list[str] = []
    params: list[Any] = []
    if q and q.strip():
        where_parts.append("(c.id_cible ILIKE %s OR c.nom_cible ILIKE %s)")
        pattern = f"%{q.strip()}%"
        params.extend([pattern, pattern])
    if source and source.strip():
        source_key = source.strip().lower()
        source_value = {"db": "DB", "file": "Fichier plat"}.get(source_key, source.strip())
        where_parts.append("c.source = %s")
        params.append(source_value)
    if date_min and date_min.strip():
        where_parts.append("c.date_creation::date >= %s::date")
        params.append(date_min.strip())
    if date_max and date_max.strip():
        where_parts.append("c.date_creation::date <= %s::date")
        params.append(date_max.strip())

    # Les filtres objectif sont appliqués AVANT pagination. ``filtre`` est un
    # TEXT historique ; la fonction SQL tolérante créée par la migration 014
    # évite qu'une ancienne valeur mal formée casse toute la liste.
    objective_json = "neoimpact_safe_jsonb(c.filtre) -> '__objectif_campagnes__'"
    if objectif_mode == "none":
        where_parts.append(f"NOT (neoimpact_safe_jsonb(c.filtre) ? '__objectif_campagnes__')")
    elif objectif_mode in {"atteint", "non_atteint"}:
        where_parts.append(f"COALESCE({objective_json} ->> 'mode', '') = %s")
        params.append(objectif_mode)
    if objectif_campaign and objectif_campaign.strip():
        where_parts.append(
            f"COALESCE({objective_json} -> 'values', '[]'::jsonb) ? %s"
        )
        params.append(objectif_campaign.strip())

    locked_expr = "EXISTS (SELECT 1 FROM campagnes ac WHERE ac.id_cible = c.id_cible AND ac.etat_campagne IN ('En cours','Planifiée'))"
    if locked is True:
        where_parts.append(locked_expr)
    elif locked is False:
        where_parts.append(f"NOT {locked_expr}")

    where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

    sort_columns = {
        'id_cible': 'c.id_cible',
        'nom_cible': 'c.nom_cible',
        'source': 'c.source',
        'date_creation': 'c.date_creation',
    }
    order_col = sort_columns.get(str(sort_by or ''), 'c.date_creation')
    order_dir = 'ASC' if str(sort_dir).lower() == 'asc' else 'DESC'

    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS total FROM cibles c{where_sql}", params)
            total_row = cur.fetchone()
            total = int((total_row or {}).get("total") or 0)

            cur.execute(
                f"""
                SELECT
                    c.id_cible,
                    c.nom_cible,
                    c.date_creation,
                    c.source,
                    c.filtre,
                    c.chemin,
                    {locked_expr} AS locked,
                    lock_camp.nom_campagne AS lock_campaign_name,
                    lock_camp.etat_campagne AS lock_campaign_state
                FROM cibles c
                LEFT JOIN LATERAL (
                    SELECT ac.nom_campagne, ac.etat_campagne
                    FROM campagnes ac
                    WHERE ac.id_cible = c.id_cible
                      AND ac.etat_campagne IN ('En cours','Planifiée')
                    ORDER BY ac.date_creation DESC NULLS LAST
                    LIMIT 1
                ) AS lock_camp ON TRUE
                {where_sql}
                ORDER BY {order_col} {order_dir} NULLS LAST, c.id_cible DESC
                LIMIT %s OFFSET %s
                """,
                [*params, row_limit, row_offset],
            )
            rows = [dict(row) for row in cur.fetchall()]

            # Cartes statistiques globales: trois agrégats légers, indépendants
            # des filtres actifs afin de garder le sens historique de l'écran.
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE c.source = 'DB') AS db_total,
                    COUNT(*) FILTER (WHERE c.source = 'Fichier plat') AS file_total,
                    COUNT(*) FILTER (WHERE {locked_expr}) AS locked_total
                FROM cibles c
                """
            )
            stats_row = dict(cur.fetchone() or {})

    items: list[dict[str, Any]] = []
    import json
    for row in rows:
        row.pop("data_source_code", None)
        if str(row.get("source") or "").strip().lower() == "db":
            raw = row.get("filtre")
            if isinstance(raw, str):
                try:
                    row["filtre"] = json.loads(raw or "{}")
                except Exception:
                    row["filtre"] = {}
        else:
            row["filtre"] = {}
        if row.get("locked"):
            name = str(row.pop("lock_campaign_name", "") or "").strip()
            state = str(row.pop("lock_campaign_state", "") or "").strip()
            row["lock_reason"] = f"Campagne '{name}' ({state})" if name or state else "Liée à une campagne active/planifiée"
        else:
            row.pop("lock_campaign_name", None)
            row.pop("lock_campaign_state", None)
            row["lock_reason"] = None
        items.append(row)

    consumed = row_offset + len(items)
    return {
        "items": items,
        "count": len(items),
        "total": total,
        "limit": per_page,
        "pages": nb_pages,
        "page_start": page_start,
        "next_page_start": page_start + nb_pages if consumed < total else None,
        "stats": {
            "total": int(stats_row.get("total") or 0),
            "locked_total": int(stats_row.get("locked_total") or 0),
            "db_total": int(stats_row.get("db_total") or 0),
            "file_total": int(stats_row.get("file_total") or 0),
        },
    }

@router.get("/cibles/objective-campaigns")
def list_objective_campaigns_for_cible_filter():
    """
    Liste légère des campagnes disponibles pour le filtre objectif.
    Ne charge que les trois colonnes nécessaires aux sélecteurs.
    """
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id_campagne, nom_campagne, etat_campagne
                FROM campagnes
                ORDER BY nom_campagne ASC, id_campagne ASC
                """
            )
            items = [
                {
                    "id_campagne": str(row.get("id_campagne") or ""),
                    "nom_campagne": str(row.get("nom_campagne") or ""),
                    "etat": str(row.get("etat_campagne") or ""),
                }
                for row in cur.fetchall()
                if row.get("id_campagne")
            ]
    return {"items": items}

@router.get("/cibles/locked")
def locked_cibles():
    locked_ids, reasons = get_locked_cibles_for_ui()
    return {"locked_ids": sorted(list(locked_ids or [])), "reasons": reasons or {}}


@router.get("/cibles/{id_cible}")
def get_cible(id_cible: str):
    return get_cible_for_ui(id_cible)


@router.get("/cibles/{id_cible}/filtre")
def get_cible_filtre(id_cible: str):
    row = get_cible_for_ui(id_cible)
    if not row:
        return {"filtre": {}}
    return {"filtre": get_cible_filtre_dict_for_ui(row)}


@router.post("/cibles/db")
def create_cible_db(payload: CibleDbCreateIn):
    _validate_segment_filter(payload.filtre)
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
    _validate_segment_filter(payload.filtre)
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
