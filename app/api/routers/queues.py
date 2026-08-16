# app/api/routers/queues.py
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.engine.crc_engine import (
    get_next_crc_input_row,
    get_next_row_from_queue,
    get_row_from_queue,
    move_row_to_end_of_queue,
    apply_result_and_update_client_campagnes,
    apply_result_and_update_client_campagnes_from_queue,
    call_current_client,
    get_arrive_eche_flag,  # ✅ flag échéance
    get_ordered_rows_from_queue,
    list_gestionnaires_in_queue,
    get_queue_counts_by_gestionnaire,
)
from app.domain.canaux import resultats_for_canal
from app.domain.ui_facades.crc_ui_facade import get_crc_context_from_db
from app.domain.ui_facades.da_ui_facade import get_da_context_from_db
from app.domain.ui_facades.cc_ui_facade import get_cc_context_from_db

router = APIRouter()

QUEUE_TABLES = {
    "crc": "crc_input",
    "da": "vers_da",
    "cc": "vers_cc",
}

# ✅ NEW: boutons "objectif" (le bloc objectif est une gate Oui/Non)
OBJECTIF_RESULTATS = ["Oui", "Non"]  # adapte si ton engine attend "Valide"/"Non valide"


class QueueKeyIn(BaseModel):
    id_campagne: str
    radical_compte: str


class ApplyResultIn(QueueKeyIn):
    resultat: str


def _get_table(queue: str) -> str:
    if queue not in QUEUE_TABLES:
        raise HTTPException(status_code=400, detail="queue_name invalide (crc|da|cc)")
    return QUEUE_TABLES[queue]


def _norm_str(x: object) -> str:
    return "" if x is None else str(x).strip()


def _compute_resultats_for_row(row: dict) -> list:
    """
    NEW:
    - si le noeud courant est un bloc objectif, on expose Oui/Non
    - sinon: comportement existant via resultats_for_canal(canal)
    """
    canal = _norm_str(row.get("Canal"))
    action = _norm_str(row.get("Action"))

    if canal.lower() == "objectif" or action.lower() == "objectif":
        return OBJECTIF_RESULTATS

    return resultats_for_canal(canal) if canal else []


@router.get("/queues/{queue}/next")
def queue_next(
    queue: str,
    id_campagne: Optional[str] = Query(default=None),
    gestionnaire: Optional[str] = Query(default=None),
):
    table = _get_table(queue)

    if queue == "crc":
        row = get_next_crc_input_row(
            id_campagne_filter=id_campagne,
            gestionnaire_filter=gestionnaire,
        )
    else:
        row = get_next_row_from_queue(
            table,
            id_campagne_filter=id_campagne,
            gestionnaire_filter=gestionnaire,
        )

    if not row:
        return {"row": None, "context": None, "resultats": [], "flags": {"arriv_eche": False}}

    # ✅ NEW: resultats gère aussi le canal Objectif
    resultats = _compute_resultats_for_row(row)

    id_camp = _norm_str(row.get("ID_CAMPAGNE"))
    rad = _norm_str(row.get("Radical_compte"))

    if queue == "crc":
        ctx = get_crc_context_from_db(id_camp, rad)
    elif queue == "da":
        ctx = get_da_context_from_db(id_camp, rad)
    else:
        ctx = get_cc_context_from_db(id_camp, rad)

    arriv_eche = get_arrive_eche_flag(id_camp, rad)

    return {
        "row": row,
        "context": ctx,
        "resultats": resultats,
        "flags": {"arriv_eche": arriv_eche},
    }


@router.post("/queues/{queue}/skip")
def queue_skip(queue: str, payload: QueueKeyIn):
    """
    Skip = passer au suivant sans perdre la tâche.
    Le comportement est identique pour CRC, CC et DA.
    """
    table = _get_table(queue)
    move_row_to_end_of_queue(
        table,
        payload.id_campagne,
        payload.radical_compte,
    )
    return {"ok": True}


@router.post("/queues/{queue}/apply-result")
def queue_apply_result(
    queue: str,
    payload: ApplyResultIn,
    id_campagne: Optional[str] = Query(default=None),
    gestionnaire: Optional[str] = Query(default=None),
):
    """
    Applique le résultat à la ligne explicitement identifiée par le payload.

    Les query params sont conservés pour compatibilité avec le frontend
    existant, mais le payload est désormais la source de vérité pour le client
    traité. On évite ainsi qu'un changement de queue applique le résultat au
    mauvais client.
    """
    table = _get_table(queue)

    row = get_row_from_queue(
        table,
        payload.id_campagne,
        payload.radical_compte,
    )

    if not row:
        return {
            "ok": False,
            "error": "queue_row_not_found",
            "id_campagne": payload.id_campagne,
            "radical_compte": payload.radical_compte,
        }

    if queue == "crc":
        return apply_result_and_update_client_campagnes(
            row,
            payload.resultat,
        )

    return apply_result_and_update_client_campagnes_from_queue(
        row,
        payload.resultat,
        table,
    )


@router.post("/queues/crc/call")
def call_current(
    id_campagne: Optional[str] = Query(default=None),
    gestionnaire: Optional[str] = Query(default=None),
):
    row = get_next_crc_input_row(
        id_campagne_filter=id_campagne,
        gestionnaire_filter=gestionnaire,
    )
    if not row:
        return {"ok": False, "error": "Queue CRC vide"}
    return call_current_client(row)


@router.get("/queues/{queue}/counts-by-gestionnaire")
def queue_counts_by_gestionnaire(
    queue: str,
    id_campagne: Optional[str] = Query(default=None),
):
    """
    Retourne le nombre d'entrées dans la queue, groupées par gestionnaire.
    queue: 'crc' | 'da' | 'cc'
    id_campagne: filtre optionnel sur une campagne
    """
    table = _get_table(queue)
    return get_queue_counts_by_gestionnaire(table, id_campagne_filter=id_campagne)


@router.get("/queues/{queue}/gestionnaires")
def queue_gestionnaires(
    queue: str,
    id_campagne: Optional[str] = Query(default=None),
):
    """
    Liste des gestionnaires présents dans la queue (distinct).
    """
    table = _get_table(queue)
    return {"gestionnaires": list_gestionnaires_in_queue(table, id_campagne_filter=id_campagne)}


@router.get("/queues/{queue}/ordered")
def queue_ordered(
    queue: str,
    id_campagne: Optional[str] = Query(default=None),
    gestionnaire: Optional[str] = Query(default=None),
):
    table = _get_table(queue)
    rows = get_ordered_rows_from_queue(
        table,
        id_campagne_filter=id_campagne,
        gestionnaire_filter=gestionnaire,
    )
    return rows
