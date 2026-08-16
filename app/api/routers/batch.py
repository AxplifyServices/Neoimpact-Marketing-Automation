from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from app.batch.batch_runner import (
    BatchAlreadyRunningError,
    run_batch_with_lock,
)
from app.batch.scheduler import get_batch_scheduler_status

router = APIRouter()


@router.post("/batch/run")
def run_batch(
    limit: int = Query(default=0, ge=0),
    dry_run: bool = Query(default=False),
) -> Dict[str, Any]:
    """
    Lance le batch manuel.

    ``limit`` et ``dry_run`` restent dans le contrat HTTP pour ne pas casser
    l'interface existante. La version métier actuelle de ``run_batch_manuel``
    ne les utilise pas.

    Le même verrou PostgreSQL que le scheduler quotidien est utilisé afin
    d'empêcher deux exécutions simultanées.
    """
    _ = limit, dry_run

    try:
        execution = run_batch_with_lock(trigger="manual_api")
        return {
            "ok": True,
            "result": execution["result"],
        }

    except BatchAlreadyRunningError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "BATCH_ALREADY_RUNNING",
                "message": str(exc),
            },
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "BATCH_RUN_FAILED",
                "message": str(exc),
            },
        ) from exc


@router.get("/batch/schedule")
def batch_schedule() -> Dict[str, Any]:
    """Expose la configuration et la prochaine exécution automatique."""
    return {
        "ok": True,
        "schedule": get_batch_scheduler_status(),
    }
