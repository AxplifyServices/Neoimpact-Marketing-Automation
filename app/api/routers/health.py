from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.storage.postgres_db import healthcheck as postgres_healthcheck, pool_stats
from app.orchestration.campaign_worker import orchestration_worker_status
from app.orchestration.job_store import orchestration_stats
from app.outbound.worker import worker_status as outbound_worker_status
from app.outbound.store import stats as outbound_stats
from app.inbound.worker import worker_status as inbound_worker_status
from app.inbound.store import stats as inbound_stats

router = APIRouter()


@router.get("/health")
def health():
    """Vérifie que l’API et PostgreSQL sont réellement disponibles."""
    try:
        db = postgres_healthcheck()
        return {
            "ok": True,
            "database": {
                "ok": bool(db.get("ok")),
                "name": db.get("database"),
                "user": db.get("user"),
                "tables": db.get("tables"),
                "pools": pool_stats(),
            },
            "orchestration": {
                "worker": orchestration_worker_status(),
                "jobs": orchestration_stats(),
            },
            "outbound": {
                "workers": outbound_worker_status(),
                "dispatches": outbound_stats(),
            },
            "inbound": {
                "workers": inbound_worker_status(),
                "events": inbound_stats(),
            },
        }
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "DATABASE_UNAVAILABLE",
                "message": str(exc),
            },
        ) from exc
