# app/api/routers/modeles.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.domain.canaux import (
    list_canaux,
    action_for_canal,
    resultats_for_canal,
    compteur_for_canal,
)

from app.domain.ui_facades.modeles_ui_facade import (
    # meta
    get_client_condition_fields_for_ui,
    get_clients_campagnes_condition_fields_for_ui,
    get_variable_choices_for_ui,
    # crud
    list_modeles_for_ui,
    get_locked_modele_ids_for_ui,
    delete_modele_for_ui,
    get_modele_edit_payload_for_ui,
    save_modele_for_ui,
    get_modele_by_id_for_ui,
    # objectif multi uniquement (si ton front en a besoin)
    build_multi_objectif_json_for_ui,
)

router = APIRouter()


# =========================================================
# Payloads
# =========================================================
class ModeleSaveIn(BaseModel):
    """
    IMPORTANT (compat front) :
    - On conserve les champs legacy `variable_cible` et `objectif_value_for_store`
      pour ne pas casser le front existant.
    - MAIS : ils ne sont plus utilisés côté back avec le nouveau format.
    """

    is_editing: bool
    id_modele: Optional[str] = Field(default="")
    nom_modele: str

    # legacy (compat)
    variable_cible: Optional[str] = Field(default="")
    objectif_value_for_store: Optional[str] = Field(default=None)

    # nouveau
    blocks: List[Dict[str, Any]]


# =========================================================
# CRUD Modeles (aligné avec Streamlit via facades)
# =========================================================
@router.get("/modeles")
def list_modeles(
    limit: int = Query(default=200, ge=1, le=5000),   # taille page
    offset: int = Query(default=0, ge=0),             # page_start (0,1,2,...)
    pages: int = Query(default=1, ge=1, le=50),       # nb pages consécutives
):
    """
    Retourne la liste des modèles + champ `locked` (True/False)
    + pagination "pages" pour éviter de surcharger l'UI.

    Pagination:
      - limit = nb éléments par page
      - offset = page_start (0,1,2,...)
      - pages = nb pages consécutives
      - total max renvoyé = limit * pages
    """
    modeles = list_modeles_for_ui() or []
    locked_ids: Set[str] = set(str(x).strip() for x in (get_locked_modele_ids_for_ui() or []))

    # enrichissement locked (inchangé)
    for m in modeles:
        if isinstance(m, dict):
            mid = (m.get("id_modele") or m.get("id") or m.get("ID") or "").strip()
            m["locked"] = bool(mid and mid in locked_ids)
        else:
            mid = (
                getattr(m, "id_modele", None)
                or getattr(m, "id", None)
                or getattr(m, "ID", None)
                or ""
            )
            mid = str(mid).strip()
            try:
                setattr(m, "locked", bool(mid and mid in locked_ids))
            except Exception:
                pass

    # pagination "pages"
    page_start = int(offset or 0)
    per_page = int(limit or 200)
    nb_pages = int(pages or 1)

    start = page_start * per_page
    end = start + (per_page * nb_pages)

    items = modeles[start:end]

    return {
        "items": items,
        "count": int(len(items)),
        "total": int(len(modeles)),
        "limit": per_page,
        "pages": nb_pages,
        "page_start": page_start,
        "next_page_start": page_start + nb_pages if end < len(modeles) else None,
    }


@router.get("/modeles/{id_modele}")
def get_modele(id_modele: str):
    return get_modele_by_id_for_ui(id_modele)


@router.get("/modeles/{id_modele}/edit-payload")
def edit_payload(id_modele: str):
    return get_modele_edit_payload_for_ui(id_modele)


@router.get("/modeles/locked")
def locked_modeles():
    locked = sorted(list(set(str(x).strip() for x in (get_locked_modele_ids_for_ui() or []))))
    return {"locked_ids": locked}


@router.delete("/modeles/{id_modele}")
def delete_modele(id_modele: str):
    id_modele = (id_modele or "").strip()
    locked_ids = set(str(x).strip() for x in (get_locked_modele_ids_for_ui() or []))

    if id_modele in locked_ids:
        raise HTTPException(
            status_code=409,
            detail="Suppression impossible : ce modèle est lié à une campagne active/planifiée.",
        )

    delete_modele_for_ui(id_modele)
    return {"ok": True}


@router.post("/modeles/save")
def save_modele(payload: ModeleSaveIn):
    """
    Compat front :
    - accepte toujours variable_cible / objectif_value_for_store
    Nouveau back :
    - on ne les utilise plus
    - on enregistre uniquement blocks (nouveau format)
    """
    try:
        save_modele_for_ui(
            is_editing=payload.is_editing,
            id_modele=(payload.id_modele or "").strip(),
            nom_modele=payload.nom_modele,
            blocks=payload.blocks,
        )
        return {"ok": True}

    except ValueError as e:
        # Erreur de validation métier
        raise HTTPException(status_code=400, detail=str(e))

    except Exception:
        # erreur inattendue => 500 mais message propre
        raise HTTPException(
            status_code=500,
            detail="Erreur interne lors de l'enregistrement du modèle.",
        )


# =========================================================
# Meta endpoints (pour reconstruire les dropdowns/boutons côté front)
# =========================================================
@router.get("/meta/variables")
def variables_meta():
    variable_choices, categorical_cols_allowed, numeric_cols = get_variable_choices_for_ui()
    return {
        "variable_choices": variable_choices,
        "categorical_cols_allowed": categorical_cols_allowed,
        "numeric_cols": numeric_cols,
    }


@router.post("/meta/objectif/build-multi")
def build_multi_objectif(payload: Dict[str, Any]):
    """
    Objectif MULTI uniquement (si ton UI le requiert encore).
    payload:
      - op: "AND" / "OR"
      - items: liste d'items objectifs
    """
    op = payload.get("op", "")
    items = payload.get("items", [])
    return {"objectif_json": build_multi_objectif_json_for_ui(op, items)}


@router.get("/meta/conditions/clients-fields")
def clients_condition_fields():
    """
    Champs utilisables dans les conditions basées sur la table `clients`.
    """
    return {"fields": get_client_condition_fields_for_ui()}


@router.get("/meta/conditions/clients-campagnes-fields")
def clients_campagnes_condition_fields():
    return {"fields": get_clients_campagnes_condition_fields_for_ui()}


@router.get("/meta/canaux")
def canaux_meta():
    canaux = list_canaux()
    return {
        "canaux": canaux,
        "actions_by_canal": {c: action_for_canal(c) for c in canaux},
        "resultats_by_canal": {c: resultats_for_canal(c) for c in canaux},
        "compteur_by_canal": {c: compteur_for_canal(c) for c in canaux},
    }
