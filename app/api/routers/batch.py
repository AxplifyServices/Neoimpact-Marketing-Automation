from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from app.batch.request_store import enqueue_request, latest_request
from app.core.workload_governor import workload_snapshot
from app.orchestration.job_store import orchestration_stats
from app.targeting.store import targeting_stats
from app.workers.runtime import latest_live_worker_details, worker_group_status

router = APIRouter()


def _schedule_status() -> Dict[str, Any]:
    details = latest_live_worker_details("batch")
    schedule = details.get("schedule") if isinstance(details, dict) else None
    if isinstance(schedule, dict):
        return schedule

    # Le worker peut être en cours de redémarrage : on expose tout de même la
    # configuration attendue sans lancer de scheduler dans l'API.
    from app.batch.scheduler import get_scheduler_config

    config = get_scheduler_config()
    return {
        "enabled": bool(config["enabled"]),
        "running": False,
        "timezone": config["timezone_name"],
        "hour": int(config["hour"]),
        "minute": int(config["minute"]),
        "next_run_time": None,
    }


@router.post("/batch/run")
def run_batch(
    limit: int = Query(default=0, ge=0),
    dry_run: bool = Query(default=False),
) -> Dict[str, Any]:
    """Demande un batch manuel sans exécuter le traitement dans le processus API."""
    created, request = enqueue_request(
        trigger="manual_api",
        parameters={"limit": int(limit), "dry_run": bool(dry_run)},
    )
    if not created:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "BATCH_ALREADY_QUEUED",
                "message": "Un batch manuel est déjà demandé ou en cours.",
                "request": request,
            },
        )
    return {
        "ok": True,
        "started": True,
        "queued": True,
        "request_id": request.get("id"),
        "message": "Batch transmis au worker dédié.",
    }


@router.get("/batch/status")
def batch_status() -> Dict[str, Any]:
    return {
        "ok": True,
        "manual": latest_request(),
        "schedule": _schedule_status(),
        "worker": worker_group_status("batch"),
        "workload": workload_snapshot(),
        "orchestration": orchestration_stats(),
        "targeting": targeting_stats(),
    }


@router.get("/batch/schedule")
def batch_schedule() -> Dict[str, Any]:
    return {
        "ok": True,
        "schedule": _schedule_status(),
        "worker": worker_group_status("batch"),
    }
