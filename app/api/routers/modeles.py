from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.domain.canaux import (
    list_canaux,
    action_for_canal,
    resultats_for_canal,
    compteur_for_canal,
)

from app.domain.ui_facades.modeles_ui_facade import (
    get_variable_choices_for_ui,
    is_categorical_positive_objectif_for_ui,
    build_numeric_objectif_json_for_ui,
    numeric_objectif_prefill_for_ui,
    list_modeles_for_ui,
    get_locked_modele_ids_for_ui,
    delete_modele_for_ui,
    get_modele_edit_payload_for_ui,
    save_modele_for_ui,
    get_modele_by_id_for_ui,
)

router = APIRouter()


# =========================================================
# Payloads
# =========================================================
class ModeleSaveIn(BaseModel):
    is_editing: bool
    id_modele: Optional[str] = ""
    nom_modele: str
    variable_cible: str
    objectif_value_for_store: str
    blocks: List[Dict[str, Any]]


# =========================================================
# CRUD Modeles (aligné avec Streamlit via facades)
# =========================================================
@router.get("/modeles")
def list_modeles():
    """
    Retourne la liste des modèles + champ `locked` (True/False)
    pour permettre à l'UI d'afficher directement l'état verrouillé.
    """
    modeles = list_modeles_for_ui()
    locked_ids = set(get_locked_modele_ids_for_ui())

    # On enrichit sans casser la structure existante
    for m in modeles:
        if isinstance(m, dict):
            mid = m.get("id_modele") or m.get("id") or m.get("ID")
            m["locked"] = bool(mid in locked_ids)
        else:
            mid = getattr(m, "id_modele", None) or getattr(m, "id", None) or getattr(m, "ID", None)
            try:
                setattr(m, "locked", bool(mid in locked_ids))
            except Exception:
                pass

    return modeles


@router.get("/modeles/{id_modele}")
def get_modele(id_modele: str):
    # Optionnel: on pourrait aussi enrichir ici avec locked,
    # mais la demande principale était sur la liste.
    return get_modele_by_id_for_ui(id_modele)


@router.get("/modeles/{id_modele}/edit-payload")
def edit_payload(id_modele: str):
    return get_modele_edit_payload_for_ui(id_modele)


@router.get("/modeles/locked")
def locked_modeles():
    locked = sorted(list(get_locked_modele_ids_for_ui()))
    return {"locked_ids": locked}



from fastapi import HTTPException

@router.delete("/modeles/{id_modele}")
def delete_modele(id_modele: str):
    id_modele = (id_modele or "").strip()
    locked_ids = set(str(x).strip() for x in get_locked_modele_ids_for_ui())

    if id_modele in locked_ids:
        raise HTTPException(
            status_code=409,
            detail="Suppression impossible : ce modèle est lié à une campagne active/planifiée."
        )

    delete_modele_for_ui(id_modele)
    return {"ok": True}



@router.post("/modeles/save")
def save_modele(payload: ModeleSaveIn):
    save_modele_for_ui(
        is_editing=payload.is_editing,
        id_modele=payload.id_modele or "",
        nom_modele=payload.nom_modele,
        variable_cible=payload.variable_cible,
        objectif_value_for_store=payload.objectif_value_for_store,
        blocks=payload.blocks,
    )
    return {"ok": True}


# =========================================================
# Meta endpoints (pour reconstruire exactement les mêmes dropdowns/boutons que Streamlit)
# =========================================================
@router.get("/meta/variables")
def variables_meta():
    variable_choices, categorical_cols_allowed, numeric_cols = get_variable_choices_for_ui()
    return {
        "variable_choices": variable_choices,
        "categorical_cols_allowed": categorical_cols_allowed,
        "numeric_cols": numeric_cols,
    }


@router.get("/meta/objectif/is-categorical-positive")
def is_cat_positive(variable_cible: str):
    return {
        "ok": True,
        "is_categorical_positive": is_categorical_positive_objectif_for_ui(variable_cible),
    }


@router.get("/meta/objectif/numeric-prefill")
def numeric_prefill(objectif: str):
    pre_min, pre_max = numeric_objectif_prefill_for_ui(objectif)
    return {"pre_min": pre_min, "pre_max": pre_max}


@router.post("/meta/objectif/build-numeric-json")
def build_numeric_json(min_txt: str = "", max_txt: str = ""):
    """
    Retourne un objectif JSON string comme en Streamlit:
    {"min": ..., "max": ...} (min/max optionnels)
    """
    return {"objectif_json": build_numeric_objectif_json_for_ui(min_txt, max_txt)}


@router.get("/meta/canaux")
def canaux_meta():
    canaux = list_canaux()
    return {
        "canaux": canaux,
        "actions_by_canal": {c: action_for_canal(c) for c in canaux},
        "resultats_by_canal": {c: resultats_for_canal(c) for c in canaux},
        "compteur_by_canal": {c: compteur_for_canal(c) for c in canaux},
    }


# NOTE:
# On SUPPRIME volontairement /meta/modalites ici.
# Les modalités (valeurs distinctes) se gèrent déjà via:
# - /api/clients/distinct?column=... (dans cibles.py)
# et/ou via la logique UI existante.
