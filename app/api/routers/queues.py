from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.engine.crc_engine import (
    get_next_crc_input_row,
    get_next_row_from_queue,
    skip_current_row,
    delete_row_from_queue,
    apply_result_and_update_client_campagnes,
    apply_result_and_update_client_campagnes_from_queue,
    call_current_client,
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
def queue_next(queue: str):
    table = _get_table(queue)

    if queue == "crc":
        row = get_next_crc_input_row()
    else:
        row = get_next_row_from_queue(table)

    if not row:
        return {"row": None, "context": None, "resultats": []}

    canal = str(row.get("Canal", "")).strip()
    resultats = resultats_for_canal(canal) if canal else []

    # context
    id_camp = str(row.get("ID_CAMPAGNE", "")).strip()
    rad = str(row.get("Radical_compte", "")).strip()

    if queue == "crc":
        ctx = get_crc_context_from_db(id_camp, rad)
    elif queue == "da":
        ctx = get_da_context_from_db(id_camp, rad)
    else:
        ctx = get_cc_context_from_db(id_camp, rad)

    return {"row": row, "context": ctx, "resultats": resultats}

@router.post("/queues/{queue}/skip")
def queue_skip(queue: str, payload: QueueKeyIn):
    table = _get_table(queue)
    if queue == "crc":
        skip_current_row(payload.id_campagne, payload.radical_compte)
    else:
        delete_row_from_queue(table, payload.id_campagne, payload.radical_compte)
    return {"ok": True}

@router.post("/queues/{queue}/apply-result")
def queue_apply_result(queue: str, payload: ApplyResultIn):
    table = _get_table(queue)

    # On a besoin de la row complète: on la relit via "next" logique
    # (simple et cohérent avec Streamlit: l'opérateur traite la première ligne)
    if queue == "crc":
        row = get_next_crc_input_row()
        if not row:
            return {"ok": False, "error": "Queue vide"}
        res = apply_result_and_update_client_campagnes(row, payload.resultat)
    else:
        row = get_next_row_from_queue(table)
        if not row:
            return {"ok": False, "error": "Queue vide"}
        res = apply_result_and_update_client_campagnes_from_queue(row, payload.resultat, table)

    return res

@router.post("/queues/crc/call")
def call_current():
    row = get_next_crc_input_row()
    if not row:
        return {"ok": False, "error": "Queue CRC vide"}
    return call_current_client(row)
