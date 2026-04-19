# app/api/routers/campagnes.py
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.storage.campagnes_store_sqlite import list_all_campagnes
from app.domain.ui_facades.campagne_ui_facade import (
    get_campagnes_affichables_for_ui,
    get_modele_choices_for_ui,
    get_cible_choices_for_ui,
    get_modele_graph_payload_for_ui,
)

# KPI dashboard (réutilisation existant)
import app.domain.dashboard_kpis as dashboard_kpis

# Actions campagne (cycle de vie + création)
from app.domain.campagne_service import (
    create_campagne as _create_campagne,
    annuler_campagne as _annuler_campagne,
    mettre_en_pause_campagne as _mettre_en_pause_campagne,
    activer_campagne as _activer_campagne,
)

router = APIRouter()


# =========================================================
# Payloads
# =========================================================
class CampagneCreateIn(BaseModel):
    nom_campagne: str
    id_modele: str
    id_cible: str
    date_debut: str
    date_fin: str
    description: Optional[str] = Field(default="")
    type_campagne: Optional[str] = Field(default="sans_action_terrain")


# =========================================================
# Helpers
# =========================================================
def _norm_str(x: Any) -> str:
    return "" if x is None else str(x).strip()


def _campaign_etat(c: Dict[str, Any]) -> str:
    # DB = Etat_campagne ; fallback compat
    return _norm_str(c.get("Etat_campagne") or c.get("etat_campagne") or c.get("etat"))


def _to_int(v: Any) -> int:
    try:
        return int(v or 0)
    except Exception:
        return 0


def _get_dashboard_kpis_for_campaign(id_campagne: str) -> Dict[str, Any]:
    """
    Utilise STRICTEMENT l'existant:
      - dashboard_kpis.DashboardFilters
      - dashboard_kpis.compute_dashboard_payload

    Mapping:
      nb_attribues      <- transmis
      nb_contactes      <- contactes_total
      nb_conversions    <- closing_total   (⚠️ si tu as déjà migré dashboard_kpis vers conversion,
                                            laisse la clé de sortie "nb_conversions" identique
                                            pour ne pas casser le front)
      nb_en_traitement  <- traitements_total
      nb_arriv_eche     <- arriv_eche
    """
    if not id_campagne:
        return {
            "nb_attribues": 0,
            "nb_conversions": 0,
            "nb_contactes": 0,
            "nb_en_traitement": 0,
            "nb_arriv_eche": 0,
        }

    try:
        filters = dashboard_kpis.DashboardFilters(campagne_ids=[id_campagne])
        payload = dashboard_kpis.compute_dashboard_payload(filters) or {}
        k = (payload.get("kpis") or {}) if isinstance(payload, dict) else {}
    except Exception:
        # ne jamais casser l'API si le dashboard a un souci
        k = {}

    return {
        "nb_attribues": _to_int(k.get("transmis", 0)),
        "nb_conversions": _to_int(k.get("closing_total", 0)),
        "nb_contactes": _to_int(k.get("contactes_total", 0)),
        "nb_en_traitement": _to_int(k.get("traitements_total", 0)),
        "nb_arriv_eche": _to_int(k.get("arriv_eche", 0)),
    }


def _enrich_campaign_with_kpis(c: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(c)
    id_campagne = _norm_str(out.get("id_campagne") or out.get("ID_CAMPAGNE"))
    out.update(_get_dashboard_kpis_for_campaign(id_campagne))

    # alias safe "etat" si front l'utilise
    if "etat" not in out:
        if "etat_campagne" in out:
            out["etat"] = out.get("etat_campagne")
        elif "Etat_campagne" in out:
            out["etat"] = out.get("Etat_campagne")

    return out


# =========================================================
# Endpoints Campagnes
# =========================================================
@router.get("/campagnes")
def list_campagnes(
    etat: Optional[str] = "affichables",
    limit: int = Query(default=500, ge=1, le=5000),   # taille page
    offset: int = Query(default=0, ge=0),             # page_start
    pages: int = Query(default=1, ge=1, le=50),       # nb pages à charger
):
    """
    - etat=affichables : campagnes UI + ajoute Annulées/Terminées
    - sinon : renvoie toutes les campagnes
    - toujours enrichi avec KPI dashboard filtrés par campagne

    Pagination:
      - limit = nb éléments par page
      - offset = page_start (0,1,2,...)
      - pages = nb pages consécutives
      - total max renvoyé = limit * pages
    """

    # ---------- 1) Construire la liste complète (comportement actuel) ----------
    if etat == "affichables":
        base = get_campagnes_affichables_for_ui() or []
        base_by_id = {
            _norm_str(x.get("id_campagne") or x.get("ID_CAMPAGNE")): x
            for x in base
            if _norm_str(x.get("id_campagne") or x.get("ID_CAMPAGNE"))
        }

        all_c = list_all_campagnes() or []
        for c in all_c:
            et = _campaign_etat(c)
            if et in ("Annulée", "Terminée"):
                cid = _norm_str(c.get("id_campagne") or c.get("ID_CAMPAGNE"))
                if cid and cid not in base_by_id:
                    base_by_id[cid] = c

        all_items = [_enrich_campaign_with_kpis(c) for c in base_by_id.values()]
    else:
        all_c = list_all_campagnes() or []
        all_items = [_enrich_campaign_with_kpis(c) for c in all_c]

    # ---------- 2) Pagination "pages" ----------
    page_start = int(offset or 0)
    per_page = int(limit or 500)
    nb_pages = int(pages or 1)

    start = page_start * per_page
    end = start + (per_page * nb_pages)

    page_items = all_items[start:end]

    return {
        "etat": etat,
        "items": page_items,
        "count": int(len(page_items)),
        "total": int(len(all_items)),
        "limit": per_page,
        "pages": nb_pages,
        "page_start": page_start,
        "next_page_start": page_start + nb_pages if end < len(all_items) else None,
    }


@router.post("/campagnes")
def create_campagne_endpoint(payload: CampagneCreateIn):
    """
    Crée une campagne.

    IMPORTANT:
    - la logique "variable_cible / objectif modèle" n'existe plus
    - on s'appuie sur campagne_service.create_campagne (root bloc + mail init + routage)
    - on ne change pas le shape de réponse (front safe)
    """
    try:
        return _create_campagne(
            nom_campagne=payload.nom_campagne,
            id_modele=payload.id_modele,
            id_cible=payload.id_cible,
            date_debut=payload.date_debut,
            date_fin=payload.date_fin,
            etat_campagne=None,
            description=payload.description,
            type_campagne=payload.type_campagne,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/campagnes/{id_campagne}/annuler")
def annuler_campagne(id_campagne: str):
    """
    Annule une campagne : état=Annulée + purge queues.
    """
    res = _annuler_campagne(id_campagne)
    if not res.get("ok", True):
        raise HTTPException(status_code=400, detail=res.get("error", "Annulation impossible"))
    return res


@router.post("/campagnes/{id_campagne}/pause")
def pause_campagne(id_campagne: str):
    """
    Pause une campagne : état=En pause + purge queues.
    """
    res = _mettre_en_pause_campagne(id_campagne)
    if not res.get("ok", True):
        raise HTTPException(status_code=400, detail=res.get("error", "Mise en pause impossible"))
    return res


@router.post("/campagnes/{id_campagne}/activer")
def activer_campagne(id_campagne: str):
    """
    Réactive une campagne en pause : recalcul état + réimport + rebuild queues.
    """
    res = _activer_campagne(id_campagne)
    if not res.get("ok", True):
        raise HTTPException(status_code=400, detail=res.get("error", "Activation impossible"))
    return res


# =========================================================
# Endpoints META (additifs -> ne cassent rien)
# =========================================================
@router.get("/campagnes/meta/modele-choices")
def modele_choices():
    """
    Permet au front d'afficher la liste des modèles (labels + mapping label->id).
    """
    labels, mapping = get_modele_choices_for_ui()
    return {"labels": labels, "mapping": mapping}


@router.get("/campagnes/meta/cible-choices")
def cible_choices():
    """
    Permet au front d'afficher la liste des cibles (labels + mapping label->id).
    """
    labels, mapping = get_cible_choices_for_ui()
    return {"labels": labels, "mapping": mapping}


@router.get("/campagnes/meta/modele-graph")
def modele_graph(id_modele: str = Query(..., min_length=1)):
    """
    Payload UI pour afficher le graphe du modèle (liste_action + graphe_json).
    """
    payload = get_modele_graph_payload_for_ui(id_modele)
    if not payload:
        raise HTTPException(status_code=404, detail="Modèle introuvable")
    return payload
