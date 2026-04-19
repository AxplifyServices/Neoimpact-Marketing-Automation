from __future__ import annotations

import os
import secrets
import sqlite3
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from app.storage.db import DB_PATH
from app.engine.crc_engine import (
    get_next_row_from_queue,
    apply_result_and_update_client_campagnes_from_queue,
    get_arrive_eche_flag,
    get_ordered_rows_from_queue,
    list_gestionnaires_in_queue,
    get_queue_counts_by_gestionnaire,
)
from app.domain.canaux import resultats_for_canal
from app.domain.ui_facades.da_ui_facade import get_da_context_from_db
from app.domain.ui_facades.cc_ui_facade import get_cc_context_from_db

router = APIRouter()

QUEUE_TABLES = {
    "da": "vers_da_terrain",
    "cc": "vers_cc_terrain",
}

OBJECTIF_RESULTATS = ["Oui", "Non"]

TERRAIN_API_KEY = (os.environ.get("TERRAIN_API_KEY") or "").strip()


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _check_api_key(x_api_key: str) -> None:
    expected = TERRAIN_API_KEY
    provided = (x_api_key or "").strip()

    if not expected:
        raise HTTPException(
            status_code=500,
            detail="TERRAIN_API_KEY non configurée côté serveur",
        )

    if not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _ensure_terrain_logs_table() -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS terrain_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_campagne TEXT,
            radical_compte TEXT,
            queue TEXT,
            action TEXT,
            resultat TEXT,
            source TEXT,
            date_event TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_terrain_log(
    *,
    id_campagne: str,
    radical_compte: str,
    queue: str,
    action: str,
    resultat: str,
    source: str = "external",
) -> None:
    _ensure_terrain_logs_table()

    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO terrain_logs (
            id_campagne,
            radical_compte,
            queue,
            action,
            resultat,
            source,
            date_event
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _norm_str(id_campagne),
            _norm_str(radical_compte),
            _norm_str(queue),
            _norm_str(action),
            _norm_str(resultat),
            _norm_str(source),
            _now_iso(),
        ),
    )
    conn.commit()
    conn.close()

class QueueKeyIn(BaseModel):
    id_campagne: str
    radical_compte: str


class ApplyResultIn(QueueKeyIn):
    resultat: str


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _get_table(queue: str) -> str:
    if queue not in QUEUE_TABLES:
        raise HTTPException(status_code=400, detail="queue_name invalide (da|cc)")
    return QUEUE_TABLES[queue]


def _norm_str(x: object) -> str:
    return "" if x is None else str(x).strip()


def _compute_resultats_for_row(row: dict) -> list:
    canal = _norm_str(row.get("Canal"))
    action = _norm_str(row.get("Action"))

    if canal.lower() == "objectif" or action.lower() == "objectif":
        return OBJECTIF_RESULTATS

    return resultats_for_canal(canal) if canal else []


def _get_row_by_key(table: str, id_campagne: str, radical_compte: str) -> Optional[dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        f"""
        SELECT *
        FROM {table}
        WHERE TRIM(ID_CAMPAGNE) = ? AND TRIM(Radical_compte) = ?
        LIMIT 1
        """,
        (str(id_campagne).strip(), str(radical_compte).strip()),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


@router.get("/terrain-queues/{queue}/next")
def queue_next(
    queue: str,
    id_campagne: Optional[str] = Query(default=None),
    gestionnaire: Optional[str] = Query(default=None),
):
    table = _get_table(queue)

    row = get_next_row_from_queue(
        table,
        id_campagne_filter=id_campagne,
        gestionnaire_filter=gestionnaire,
    )

    if not row:
        return {"row": None, "context": None, "resultats": [], "flags": {"arriv_eche": False}}

    resultats = _compute_resultats_for_row(row)

    id_camp = _norm_str(row.get("ID_CAMPAGNE"))
    rad = _norm_str(row.get("Radical_compte"))

    if queue == "da":
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


@router.post("/terrain-queues/{queue}/apply-result")
def queue_apply_result(
    queue: str,
    payload: ApplyResultIn,
    x_api_key: str = Header(default=""),
):
    _check_api_key(x_api_key)

    table = _get_table(queue)

    row = _get_row_by_key(table, payload.id_campagne, payload.radical_compte)
    if not row:
        _insert_terrain_log(
            id_campagne=payload.id_campagne,
            radical_compte=payload.radical_compte,
            queue=queue,
            action="",
            resultat=payload.resultat,
            source="external_missing_row",
        )
        return {"ok": False, "error": "Ligne introuvable dans la queue terrain"}

    _insert_terrain_log(
        id_campagne=payload.id_campagne,
        radical_compte=payload.radical_compte,
        queue=queue,
        action=_norm_str(row.get("Action")),
        resultat=payload.resultat,
        source="external",
    )

    return apply_result_and_update_client_campagnes_from_queue(row, payload.resultat, table)


@router.get("/terrain-queues/{queue}/counts-by-gestionnaire")
def queue_counts_by_gestionnaire(
    queue: str,
    id_campagne: Optional[str] = Query(default=None),
):
    table = _get_table(queue)
    return get_queue_counts_by_gestionnaire(table, id_campagne_filter=id_campagne)


@router.get("/terrain-queues/{queue}/gestionnaires")
def queue_gestionnaires(
    queue: str,
    id_campagne: Optional[str] = Query(default=None),
):
    table = _get_table(queue)
    return {"gestionnaires": list_gestionnaires_in_queue(table, id_campagne_filter=id_campagne)}


@router.get("/terrain-queues/{queue}/ordered")
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