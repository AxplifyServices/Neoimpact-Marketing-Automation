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
    gestionnaires: Optional[List[str]] = None  # ✅ déjà présent


# =========================================================
# Dynamic filters (bidirectionnels)
# (On conserve exactement la même structure de sortie pour ne pas casser le front)
# =========================================================
@router.get("/dashboard/filters")
def dashboard_filters(
    campagne_ids: Optional[List[str]] = Query(default=None),
    etats_campagne: Optional[List[str]] = Query(default=None),
    etats: Optional[List[str]] = Query(default=None),  # alias backward-compatible
):
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
    out = get_dynamic_filter_options(
        selected_campagne_ids=None,
        selected_etats=None,
    )
    return {"options": out.get("campagnes", [])}


# =========================================================
# Compute dashboard (POST)
# - Retourne toujours le GLOBAL (kpis/tables/series)
# - Et si campagne_ids fourni => payload["by_campaign"] contient tout isolé par campagne
# - Et si len(campagne_ids)==1 => payload["graph"] (compat historique)
# =========================================================
@router.post("/dashboard/compute")
def dashboard_compute(payload: DashboardIn):
    filters = DashboardFilters(
        campagne_ids=payload.campagne_ids,
        etats_campagne=payload.etats_campagne,
        date_min=payload.date_min,
        date_max=payload.date_max,
        gestionnaires=payload.gestionnaires,  # ✅ IMPORTANT : on le passe partout
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
    gestionnaires: Optional[List[str]] = Query(default=None),  # ✅ NEW
):
    filters = DashboardFilters(
        campagne_ids=campagne_ids,
        etats_campagne=etats_campagne,
        date_min=date_min,
        date_max=date_max,
        gestionnaires=gestionnaires,
    )
    return compute_dashboard_payload(filters)


# =========================================================
# Alias (optionnel) - BY CAMPAIGN
# Pour ne pas casser un front qui appelait déjà /compute-by-campagne
# (renvoie le même payload que /dashboard/compute, incluant by_campaign)
# =========================================================
@router.post("/dashboard/compute-by-campagne")
def dashboard_compute_by_campagne(payload: DashboardIn):
    # ✅ BUG FIX : tu avais oublié gestionnaires ici (ça cassait le filtre par gestionnaire)
    filters = DashboardFilters(
        campagne_ids=payload.campagne_ids,
        etats_campagne=payload.etats_campagne,
        date_min=payload.date_min,
        date_max=payload.date_max,
        gestionnaires=payload.gestionnaires,
    )
    return compute_dashboard_payload(filters)


@router.get("/dashboard/compute-by-campagne")
def dashboard_compute_by_campagne_get(
    campagne_ids: Optional[List[str]] = Query(default=None),
    etats_campagne: Optional[List[str]] = Query(default=None),
    date_min: Optional[date] = Query(default=None),
    date_max: Optional[date] = Query(default=None),
    gestionnaires: Optional[List[str]] = Query(default=None),  # ✅ NEW
):
    filters = DashboardFilters(
        campagne_ids=campagne_ids,
        etats_campagne=etats_campagne,
        date_min=date_min,
        date_max=date_max,
        gestionnaires=gestionnaires,
    )
    return compute_dashboard_payload(filters)
