from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.engine.crc_engine import (
    get_next_crc_input_row,
    get_next_row_from_queue,
    skip_current_row,
    delete_row_from_queue,
    apply_result_and_update_client_campagnes,
    apply_result_and_update_client_campagnes_from_queue,
    call_current_client,
    get_arrive_eche_flag,  # ✅ NEW: expose flag échéance
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


class QueueKeyIn(BaseModel):
    id_campagne: str
    radical_compte: str


class ApplyResultIn(QueueKeyIn):
    resultat: str


def _get_table(queue: str) -> str:
    if queue not in QUEUE_TABLES:
        raise HTTPException(status_code=400, detail="queue_name invalide (crc|da|cc)")
    return QUEUE_TABLES[queue]


@router.get("/queues/{queue}/next")
def queue_next(queue: str, id_campagne: Optional[str] = Query(default=None)):
    table = _get_table(queue)

    if queue == "crc":
        row = get_next_crc_input_row(id_campagne_filter=id_campagne)
    else:
        row = get_next_row_from_queue(table, id_campagne_filter=id_campagne)

    if not row:
        return {"row": None, "context": None, "resultats": [], "flags": {"arriv_eche": False}}

    canal = str(row.get("Canal", "")).strip()
    resultats = resultats_for_canal(canal) if canal else []

    id_camp = str(row.get("ID_CAMPAGNE", "")).strip()
    rad = str(row.get("Radical_compte", "")).strip()

    if queue == "crc":
        ctx = get_crc_context_from_db(id_camp, rad)
    elif queue == "da":
        ctx = get_da_context_from_db(id_camp, rad)
    else:
        ctx = get_cc_context_from_db(id_camp, rad)

    # ✅ NEW: flag explicite pour le front
    arriv_eche = get_arrive_eche_flag(id_camp, rad)

    return {
        "row": row,
        "context": ctx,
        "resultats": resultats,
        "flags": {"arriv_eche": arriv_eche},
    }


@router.post("/queues/{queue}/skip")
def queue_skip(queue: str, payload: QueueKeyIn):
    table = _get_table(queue)
    if queue == "crc":
        skip_current_row(payload.id_campagne, payload.radical_compte)
    else:
        delete_row_from_queue(table, payload.id_campagne, payload.radical_compte)
    return {"ok": True}


@router.post("/queues/{queue}/apply-result")
def queue_apply_result(queue: str, payload: ApplyResultIn, id_campagne: Optional[str] = Query(default=None)):
    """
    id_campagne (query param) permet d'appliquer le résultat sur la prochaine ligne de la campagne filtrée,
    cohérent avec l'UI Streamlit.
    """
    table = _get_table(queue)

    if queue == "crc":
        row = get_next_crc_input_row(id_campagne_filter=id_campagne)
        if not row:
            return {"ok": False, "error": "Queue vide"}
        return apply_result_and_update_client_campagnes(row, payload.resultat)

    row = get_next_row_from_queue(table, id_campagne_filter=id_campagne)
    if not row:
        return {"ok": False, "error": "Queue vide"}
    return apply_result_and_update_client_campagnes_from_queue(row, payload.resultat, table)


@router.post("/queues/crc/call")
def call_current(id_campagne: Optional[str] = Query(default=None)):
    row = get_next_crc_input_row(id_campagne_filter=id_campagne)
    if not row:
        return {"ok": False, "error": "Queue CRC vide"}
    return call_current_client(row)

@router.get("/queues/{queue}/ordered")
def queue_ordered(
    queue: str,
    id_campagne: Optional[str] = Query(default=None),
    gestionnaire: Optional[str] = Query(default=None),  # ✅ NEW
):
    table = _get_table(queue)
    rows = get_ordered_rows_from_queue(
        table,
        id_campagne_filter=id_campagne,
        gestionnaire_filter=gestionnaire,  # ✅ NEW
    )
    return rows


