from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.engine.contact_client_engine import apply_result_from_queue


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
    id_campagne = _norm_str(payload.correlationId)
    radical_compte = _norm_str(payload.externalClientId)
    block_id = _norm_str(payload.blockId)

    if not id_campagne or not radical_compte or not block_id:
        raise HTTPException(
            status_code=400,
            detail="correlationId, externalClientId et blockId sont obligatoires",
        )

    resultats = [_norm_str(x) for x in payload.resultats if _norm_str(x)]
    if not resultats:
        raise HTTPException(status_code=400, detail="resultats est obligatoire")

    resultat = resultats[0]

    if resultat not in ("Aboutit", "Non Aboutit"):
        raise HTTPException(
            status_code=400,
            detail="resultat invalide. Valeurs acceptées: Aboutit, Non Aboutit",
        )

    row = {
        "ID_CAMPAGNE": id_campagne,
        "Radical_compte": radical_compte,
        "ID_Action": block_id,
    }

    return apply_result_from_queue(
        row=row,
        resultat_label=resultat,
        queue_table="external_visit_dispatches",
    )