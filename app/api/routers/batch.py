from __future__ import annotations

import inspect
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from app.batch.batch_manuel import run_batch_manuel

router = APIRouter()


@router.post("/batch/run")
def run_batch(
    limit: int = Query(default=0, ge=0),
    dry_run: bool = Query(default=False),
) -> Dict[str, Any]:
    """
    Lance le batch manuel.

    Le contrat HTTP historique est conservé. Les paramètres ``limit`` et
    ``dry_run`` ne sont transmis que si la version courante du batch les
    déclare réellement. On évite ainsi de relancer le batch après un
    ``TypeError`` interne à sa logique métier.
    """
    try:
        signature = inspect.signature(run_batch_manuel)
        kwargs: Dict[str, Any] = {}

        if "limit" in signature.parameters:
            kwargs["limit"] = limit
        if "dry_run" in signature.parameters:
            kwargs["dry_run"] = dry_run

        result = run_batch_manuel(**kwargs)
        return {"ok": True, "result": result}

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "BATCH_RUN_FAILED",
                "message": str(exc),
            },
        ) from exc
