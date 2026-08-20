from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.inbound.store import enqueue_event

router = APIRouter()


def _norm_str(x: Any) -> str:
    return "" if x is None else str(x).strip()


class TerrainVisitCallbackIn(BaseModel):
    correlationId: str = Field(..., description="ID campagne")
    externalClientId: str = Field(..., description="ID client / Radical_compte")
    blockId: str = Field(..., description="ID bloc action DA/CC")
    resultats: List[str] = Field(..., description="['Aboutit'] ou ['Non Aboutit']")


@router.post("/terrain-visits/callback")
def terrain_visit_callback(payload: TerrainVisitCallbackIn) -> Dict[str, Any]:
    """Accuse réception rapidement; le workflow est traité par l'Inbound Engine."""
    id_campagne = _norm_str(payload.correlationId)
    radical_compte = _norm_str(payload.externalClientId)
    block_id = _norm_str(payload.blockId)
    if not id_campagne or not radical_compte or not block_id:
        raise HTTPException(status_code=400, detail="correlationId, externalClientId et blockId sont obligatoires")

    resultats = [_norm_str(x) for x in payload.resultats if _norm_str(x)]
    if not resultats:
        raise HTTPException(status_code=400, detail="resultats est obligatoire")
    if resultats[0] not in ("Aboutit", "Non Aboutit"):
        raise HTTPException(status_code=400, detail="resultat invalide. Valeurs acceptées: Aboutit, Non Aboutit")

    raw = {
        "correlationId": id_campagne,
        "externalClientId": radical_compte,
        "blockId": block_id,
        "resultats": resultats,
    }
    queued = enqueue_event(
        channel="TERRAIN",
        event_type="visit_result",
        payload=raw,
        id_campagne=id_campagne,
        radical_compte=radical_compte,
        block_id=block_id,
    )
    return {
        "ok": True,
        "accepted": True,
        "duplicate": bool(queued.get("duplicate")),
        "event_key": queued.get("event_key"),
    }
