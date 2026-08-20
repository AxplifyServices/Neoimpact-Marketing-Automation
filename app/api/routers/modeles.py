# app/api/routers/modeles.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from app.storage.postgres_db import connection

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
    ui_positions: Optional[Dict[str, Any]] = Field(default=None)  # NEW


# =========================================================
# CRUD Modeles (aligné avec Streamlit via facades)
# =========================================================
@router.get("/modeles")
def list_modeles(
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    pages: int = Query(default=1, ge=1, le=50),
    q: Optional[str] = Query(default=None, max_length=200),
    locked: Optional[bool] = Query(default=None),
    date_min: Optional[str] = Query(default=None, max_length=32),
    date_max: Optional[str] = Query(default=None, max_length=32),
    variable: Optional[str] = Query(default=None, max_length=200),
    sort_by: Optional[str] = Query(default=None, max_length=50),
    sort_dir: str = Query(default='desc', pattern='^(asc|desc)$'),
):
    """Liste paginée des modèles sans charger toute la table en Python."""
    page_start = int(offset or 0)
    per_page = int(limit or 200)
    nb_pages = int(pages or 1)
    row_limit = per_page * nb_pages
    row_offset = page_start * per_page

    locked_expr = "EXISTS (SELECT 1 FROM campagnes c WHERE c.id_modele = m.id_modele AND c.etat_campagne IN ('En cours','Planifiée'))"
    where_parts: list[str] = []
    params: list[Any] = []
    if q and q.strip():
        where_parts.append("(m.id_modele ILIKE %s OR m.nom_modele ILIKE %s)")
        pattern = f"%{q.strip()}%"
        params.extend([pattern, pattern])
    if date_min and date_min.strip():
        where_parts.append("m.date_creation::date >= %s::date")
        params.append(date_min.strip())
    if date_max and date_max.strip():
        where_parts.append("m.date_creation::date <= %s::date")
        params.append(date_max.strip())
    if variable and variable.strip():
        where_parts.append("COALESCE(m.variable_cible,'') = %s")
        params.append(variable.strip())
    if locked is True:
        where_parts.append(locked_expr)
    elif locked is False:
        where_parts.append(f"NOT {locked_expr}")
    where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

    sort_columns = {
        'id_modele': 'm.id_modele',
        'nom_modele': 'm.nom_modele',
        'variable_cible': 'm.variable_cible',
        'date_creation': 'm.date_creation',
    }
    order_col = sort_columns.get(str(sort_by or ''), 'm.date_creation')
    order_dir = 'ASC' if str(sort_dir).lower() == 'asc' else 'DESC'

    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS total FROM modeles m{where_sql}", params)
            total = int((cur.fetchone() or {}).get("total") or 0)
            cur.execute(
                f"""
                SELECT
                    m.id_modele,
                    m.nom_modele,
                    m.date_creation,
                    m.variable_cible,
                    m.objectif,
                    m.liste_action,
                    m.graphe_json,
                    m.ui_positions,
                    {locked_expr} AS locked
                FROM modeles m
                {where_sql}
                ORDER BY {order_col} {order_dir} NULLS LAST, m.id_modele DESC
                LIMIT %s OFFSET %s
                """,
                [*params, row_limit, row_offset],
            )
            items = [dict(row) for row in cur.fetchall()]
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE {locked_expr}) AS locked_total,
                    COUNT(DISTINCT NULLIF(TRIM(COALESCE(m.variable_cible,'')), '')) AS unique_variables
                FROM modeles m
                """
            )
            stats = dict(cur.fetchone() or {})
            cur.execute(
                """
                SELECT DISTINCT TRIM(variable_cible) AS value
                FROM modeles
                WHERE NULLIF(TRIM(COALESCE(variable_cible,'')), '') IS NOT NULL
                ORDER BY value
                LIMIT 500
                """
            )
            variable_options = [str(row.get("value")) for row in cur.fetchall() if row.get("value")]

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
            "total": int(stats.get("total") or 0),
            "locked_total": int(stats.get("locked_total") or 0),
            "unique_variables": int(stats.get("unique_variables") or 0),
        },
        "filter_options": {"variables": variable_options},
    }

@router.get("/modeles/locked")
def locked_modeles():
    locked = sorted(list(set(str(x).strip() for x in (get_locked_modele_ids_for_ui() or []))))
    return {"locked_ids": locked}


@router.get("/modeles/{id_modele}")
def get_modele(id_modele: str):
    return get_modele_by_id_for_ui(id_modele)


@router.get("/modeles/{id_modele}/edit-payload")
def edit_payload(id_modele: str):
    return get_modele_edit_payload_for_ui(id_modele)


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
            ui_positions=payload.ui_positions,
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
