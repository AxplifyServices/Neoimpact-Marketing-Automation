from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.domain.dashboard_kpis import (
    DashboardFilters,
    compute_dashboard_payload,
    get_dynamic_filter_options,
)

router = APIRouter()


# =========================================================
# Input schema
# =========================================================
class DashboardIn(BaseModel):
    campagne_ids: Optional[List[str]] = None
    etats_campagne: Optional[List[str]] = None
    date_min: Optional[date] = None
    date_max: Optional[date] = None


# =========================================================
# Dynamic filters (bidirectionnels)
# =========================================================
@router.get("/dashboard/filters")
def dashboard_filters(
    campagne_ids: Optional[List[str]] = Query(default=None),
    etats_campagne: Optional[List[str]] = Query(default=None),
    etats: Optional[List[str]] = Query(default=None),  # alias backward-compatible
):
    """
    Renvoie les options de filtres dynamiques.
    - campagne_ids : campagnes déjà sélectionnées
    - etats_campagne : états sélectionnés (OFFICIEL)
    - etats : alias rétro-compatible
    """

    # priorité au nom officiel
    effective_etats = etats_campagne if etats_campagne is not None else etats

    return get_dynamic_filter_options(
        selected_campagne_ids=campagne_ids,
        selected_etats=effective_etats,
    )


# =========================================================
# Backward-compatible endpoint (ancien front)
# =========================================================
@router.get("/dashboard/campagnes-options")
def campaign_options():
    """
    Endpoint legacy conservé pour compatibilité.
    """
    out = get_dynamic_filter_options(
        selected_campagne_ids=None,
        selected_etats=None,
    )
    return {"options": out.get("campagnes", [])}


# =========================================================
# Compute dashboard (POST)
# =========================================================
@router.post("/dashboard/compute")
def dashboard_compute(payload: DashboardIn):
    """
    Calcule KPIs + séries + tables + graphe (si 1 campagne).
    """
    filters = DashboardFilters(
        campagne_ids=payload.campagne_ids,
        etats_campagne=payload.etats_campagne,
        date_min=payload.date_min,
        date_max=payload.date_max,
    )
    return compute_dashboard_payload(filters)


# =========================================================
# Compute dashboard (GET) – utile debug / URL share
# =========================================================
@router.get("/dashboard/compute")
def dashboard_compute_get(
    campagne_ids: Optional[List[str]] = Query(default=None),
    etats_campagne: Optional[List[str]] = Query(default=None),
    date_min: Optional[date] = Query(default=None),
    date_max: Optional[date] = Query(default=None),
):
    filters = DashboardFilters(
        campagne_ids=campagne_ids,
        etats_campagne=etats_campagne,
        date_min=date_min,
        date_max=date_max,
    )
    return compute_dashboard_payload(filters)
