# app/api/routers/campagnes.py
from __future__ import annotations

from typing import Any, Dict, Optional
import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.storage.campagnes_store_sqlite import list_all_campagnes
from app.domain.ui_facades.campagne_ui_facade import (
    get_campagnes_affichables_for_ui,
    get_modele_choices_for_ui,
    get_cible_choices_for_ui,
    get_modele_graph_payload_for_ui,
)

# KPI légers pour la liste des campagnes : agrégés directement par PostgreSQL.
from app.storage.postgres_db import connection

# Actions campagne (cycle de vie + création)
from app.domain.campagne_service import (
    create_campagne as _create_campagne,
    annuler_campagne as _annuler_campagne,
    mettre_en_pause_campagne as _mettre_en_pause_campagne,
    activer_campagne as _activer_campagne,
)

from app.domain.terrain_visit_webhook import dispatch_pending_visits_for_campaign, get_terrain_dispatch_status

logger = logging.getLogger(__name__)

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

     # Uniquement utile si type_campagne = avec_action_terrain
    visitMode: Optional[str] = Field(default=None)      # A_DISTANCE | TERRAIN
    visitPurpose: Optional[str] = Field(default=None)   # COMMERCIAL | RECOUVREMENT


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


def _empty_campaign_kpis() -> Dict[str, int]:
    return {
        "nb_attribues": 0,
        "nb_conversions": 0,
        "nb_contactes": 0,
        "nb_en_traitement": 0,
        "nb_arriv_eche": 0,
    }


def _get_dashboard_kpis_for_campaign_ids(
    campagne_ids: list[str],
) -> Dict[str, Dict[str, int]]:
    """
    KPI compacts de la liste des campagnes, calculés 100% dans PostgreSQL.

    IMPORTANT PERFORMANCE:
    - aucune ligne clients_campagnes n'est matérialisée en Python;
    - aucun DataFrame Pandas;
    - une seule requête GROUP BY pour toutes les campagnes de la page.

    Les définitions restent alignées avec dashboard_kpis.compute_kpis_compact:
      nb_attribues      = nombre historique de lignes clients_campagnes
      nb_contactes      = client ayant au moins un compteur canal > 0
      nb_conversions    = conversion = 1
      nb_en_traitement  = somme des compteurs de traitements par canal
      nb_arriv_eche     = arriv_eche = 'Oui'

    Comme le dashboard historique, les campagnes Annulées ne contribuent pas
    à ces KPI.
    """
    ids = [_norm_str(x) for x in campagne_ids if _norm_str(x)]
    if not ids:
        return {}

    placeholders = ", ".join(["%s"] * len(ids))

    treatment_expr = """
        COALESCE(cc."NB_appel", 0)
      + COALESCE(cc."NB_mail", 0)
      + COALESCE(cc."NB_sms", 0)
      + COALESCE(cc."NB_message", 0)
      + COALESCE(cc."NB_da", 0)
      + COALESCE(cc."NB_cc", 0)
      + COALESCE(cc."NB_push", 0)
    """

    query = f"""
        SELECT
            cc."ID_CAMPAGNE" AS id_campagne,
            COUNT(*) AS nb_attribues,
            COUNT(*) FILTER (
                WHERE ({treatment_expr}) > 0
            ) AS nb_contactes,
            COUNT(*) FILTER (
                WHERE COALESCE(cc.conversion, 0) = 1
            ) AS nb_conversions,
            COALESCE(SUM({treatment_expr}), 0) AS nb_en_traitement,
            COUNT(*) FILTER (
                WHERE LOWER(TRIM(COALESCE(cc.arriv_eche, ''))) = 'oui'
            ) AS nb_arriv_eche
        FROM clients_campagnes AS cc
        INNER JOIN campagnes AS c
            ON c.id_campagne = cc."ID_CAMPAGNE"
        WHERE cc."ID_CAMPAGNE" IN ({placeholders})
          AND COALESCE(c.etat_campagne, '') IN (
              'Planifiée',
              'En cours',
              'En pause',
              'Terminée'
          )
        GROUP BY cc."ID_CAMPAGNE"
    """

    result: Dict[str, Dict[str, int]] = {}
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(query, ids)
            for row in cur.fetchall():
                cid = _norm_str(row.get("id_campagne"))
                if not cid:
                    continue
                result[cid] = {
                    "nb_attribues": _to_int(row.get("nb_attribues")),
                    "nb_conversions": _to_int(row.get("nb_conversions")),
                    "nb_contactes": _to_int(row.get("nb_contactes")),
                    "nb_en_traitement": _to_int(row.get("nb_en_traitement")),
                    "nb_arriv_eche": _to_int(row.get("nb_arriv_eche")),
                }

    return result


def _get_dashboard_kpis_for_campaign(id_campagne: str) -> Dict[str, int]:
    if not _norm_str(id_campagne):
        return _empty_campaign_kpis()
    return _get_dashboard_kpis_for_campaign_ids([id_campagne]).get(
        _norm_str(id_campagne),
        _empty_campaign_kpis(),
    )

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

        all_items = list(base_by_id.values())
    else:
        all_items = list_all_campagnes() or []

    # ---------- 2) Pagination AVANT les KPI ----------
    # On ne calcule jamais les KPI de campagnes qui ne sont pas présentes
    # dans la page demandée.
    page_start = int(offset or 0)
    per_page = int(limit or 500)
    nb_pages = int(pages or 1)

    start = page_start * per_page
    end = start + (per_page * nb_pages)

    page_base_items = all_items[start:end]

    # ---------- 3) Une seule agrégation SQL pour toute la page ----------
    page_ids = [
        _norm_str(c.get("id_campagne") or c.get("ID_CAMPAGNE"))
        for c in page_base_items
    ]
    kpis_by_campaign = _get_dashboard_kpis_for_campaign_ids(page_ids)

    page_items = []
    for campaign in page_base_items:
        out = dict(campaign)
        cid = _norm_str(out.get("id_campagne") or out.get("ID_CAMPAGNE"))
        out.update(kpis_by_campaign.get(cid, _empty_campaign_kpis()))

        if "etat" not in out:
            if "etat_campagne" in out:
                out["etat"] = out.get("etat_campagne")
            elif "Etat_campagne" in out:
                out["etat"] = out.get("Etat_campagne")

        page_items.append(out)

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
            visitMode=payload.visitMode,
            visitPurpose=payload.visitPurpose,
        )
    except Exception as e:
        logger.exception("Échec de création de campagne")
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

@router.post("/campagnes/{id_campagne}/dispatch-terrain")
def dispatch_terrain_for_campaign(id_campagne: str):
    """
    Envoie vers la plateforme terrain tous les clients actuellement positionnés
    sur un bloc DA/CC d'une campagne avec action terrain.

    Sécurisé anti-doublon via external_visit_dispatches :
    un même client + bloc n'est pas renvoyé si déjà envoyé.
    """
    try:
        return dispatch_pending_visits_for_campaign(id_campagne)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/campagnes/{id_campagne}/dispatch-terrain/status")
def dispatch_terrain_status(id_campagne: str):
    return {"ok": True, "dispatch": get_terrain_dispatch_status(id_campagne)}
    
# =========================================================
# Endpoints META (additifs -> ne cassent rien)
# =========================================================

@router.get("/campagnes/meta/create-options")
def campaign_create_options():
    """
    Options légères pour la modale de création de campagne.
    Retourne uniquement les champs réellement affichés dans les deux sélecteurs.
    """
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id_modele, nom_modele, date_creation
                FROM modeles
                ORDER BY date_creation DESC NULLS LAST, id_modele DESC
                """
            )
            modeles = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT id_cible, nom_cible, source, date_creation
                FROM cibles
                ORDER BY date_creation DESC NULLS LAST, id_cible DESC
                """
            )
            cibles = [dict(row) for row in cur.fetchall()]

    return {
        "modeles": modeles,
        "cibles": cibles,
    }


@router.get("/campagnes/meta/active-choices")
def active_campaign_choices():
    """
    Liste légère destinée aux sélecteurs CRC/Terrain.
    Évite de charger les campagnes complètes et leurs KPI.
    """
    query = """
        SELECT id_campagne, nom_campagne, etat_campagne, type_campagne
        FROM campagnes
        WHERE etat_campagne = 'En cours'
        ORDER BY nom_campagne ASC, id_campagne ASC
    """
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = [dict(row) for row in cur.fetchall()]

    return {"items": rows, "count": len(rows)}


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
