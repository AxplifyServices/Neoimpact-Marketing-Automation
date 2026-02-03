from __future__ import annotations

from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.storage.campagnes_store_sqlite import list_all_campagnes
from app.domain.ui_facades.campagne_ui_facade import get_campagnes_affichables_for_ui

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


class CampagneCreateIn(BaseModel):
    nom_campagne: str
    id_modele: str
    id_cible: str
    date_debut: str
    date_fin: str
    description: Optional[str] = ""


def _norm_str(x: Any) -> str:
    return "" if x is None else str(x).strip()


def _campaign_etat(c: Dict[str, Any]) -> str:
    # DB = etat_campagne ; fallback compat
    return _norm_str(c.get("etat_campagne") or c.get("Etat_campagne") or c.get("etat"))


def _get_dashboard_kpis_for_campaign(id_campagne: str) -> Dict[str, Any]:
    """
    Utilise STRICTEMENT l'existant:
      - dashboard_kpis.DashboardFilters
      - dashboard_kpis.compute_dashboard_payload

    Mapping:
      nb_attribues      <- transmis
      nb_contactes      <- contactes_total
      nb_conversions    <- closing_total
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

    def _to_int(v: Any) -> int:
        try:
            return int(v or 0)
        except Exception:
            return 0

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
    if "etat" not in out and "etat_campagne" in out:
        out["etat"] = out.get("etat_campagne")

    return out


@router.get("/campagnes")
def list_campagnes(etat: Optional[str] = "affichables"):
    """
    - etat=affichables : campagnes UI + ajoute Annulées/Terminées
    - sinon : renvoie toutes les campagnes
    - toujours enrichi avec KPI dashboard filtrés par campagne
    """
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

        return [_enrich_campaign_with_kpis(c) for c in base_by_id.values()]

    all_c = list_all_campagnes() or []
    return [_enrich_campaign_with_kpis(c) for c in all_c]


@router.post("/campagnes")
def create_campagne_endpoint(payload: CampagneCreateIn):
    """
    Crée une campagne.
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
