from __future__ import annotations

from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

from app.domain.campagne_service import (
    create_campagne,
    annuler_campagne,
    mettre_en_pause_campagne,
    activer_campagne,
)
from app.domain.ui_facades.campagne_ui_facade import (
    get_campagnes_affichables_for_ui,
    get_modele_choices_for_ui,
    get_cible_choices_for_ui,
    get_modele_graph_payload_for_ui,
)

router = APIRouter()


class CampagneCreateIn(BaseModel):
    nom_campagne: str
    id_modele: str
    id_cible: str
    date_debut: str  # ISO yyyy-mm-dd
    date_fin: str    # ISO yyyy-mm-dd
    description: Optional[str] = ""  # ✅ NEW


@router.get("/campagnes")
def list_campagnes(etat: Optional[str] = "affichables"):
    if etat == "affichables":
        return get_campagnes_affichables_for_ui()
    # fallback: pour l'instant on renvoie pareil
    return get_campagnes_affichables_for_ui()


@router.get("/campagnes/choices")
def campagne_choices():
    modele_labels, modele_map = get_modele_choices_for_ui()
    cible_labels, cible_map = get_cible_choices_for_ui()
    return {
        "modeles": [{"label": l, "id": modele_map[l]} for l in modele_labels],
        "cibles": [{"label": l, "id": cible_map[l]} for l in cible_labels],
    }


@router.post("/campagnes")
def create_campaign(payload: CampagneCreateIn):
    return create_campagne(
        nom_campagne=payload.nom_campagne,
        id_modele=payload.id_modele,
        id_cible=payload.id_cible,
        date_debut=payload.date_debut,
        date_fin=payload.date_fin,
        description=payload.description,  # ✅ NEW
    )


@router.post("/campagnes/{id_campagne}/pause")
def pause_campaign(id_campagne: str):
    return mettre_en_pause_campagne(id_campagne)


@router.post("/campagnes/{id_campagne}/activate")
def activate_campaign(id_campagne: str):
    return activer_campagne(id_campagne)


@router.post("/campagnes/{id_campagne}/cancel")
def cancel_campaign(id_campagne: str):
    annuler_campagne(id_campagne)
    return {"ok": True}


@router.get("/campagnes/{id_campagne}/modele-graph")
def campagne_modele_graph(id_campagne: str, id_modele: str):
    # côté Streamlit, l’id_modele vient de la campagne
    return get_modele_graph_payload_for_ui(id_modele)
