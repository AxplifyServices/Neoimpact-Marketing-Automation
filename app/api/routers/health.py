from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.inbound.store import stats as inbound_stats
from app.orchestration.job_store import orchestration_stats
from app.outbound.store import stats as outbound_stats
from app.storage.postgres_db import connection, healthcheck as postgres_healthcheck, pool_stats
from app.targeting.store import targeting_stats
from app.workers.runtime import worker_group_status

router = APIRouter()


@router.get("/health/ready")
def readiness():
    """Healthcheck léger pour Docker/Traefik : API vivante + PostgreSQL joignable.

    Le endpoint détaillé /health calcule aussi les profondeurs de queues et les
    états des workers ; il ne doit pas être appelé toutes les cinq secondes par
    Docker sur une plateforme fortement chargée.
    """
    try:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                row = cur.fetchone()
        if not row or int(row[0]) != 1:
            raise RuntimeError("PostgreSQL readiness check invalide")
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "DATABASE_UNAVAILABLE", "message": str(exc)},
        ) from exc


@router.get("/health")
def health():
    """Vérifie l'API, PostgreSQL et l'état des processus workers dédiés."""
    try:
        db = postgres_healthcheck()
        campaign_worker = worker_group_status("campaign")
        outbound_worker = worker_group_status("outbound")
        inbound_worker = worker_group_status("inbound")
        batch_worker = worker_group_status("batch")
        segmentation_worker = worker_group_status("segmentation")
        attrition_worker = worker_group_status("attrition")
        digital_engagement_worker = worker_group_status("digital_engagement")
        best_channel_worker = worker_group_status("best_channel")
        commercial_pressure_worker = worker_group_status("commercial_pressure")
        return {
            "ok": True,
            "database": {
                "ok": bool(db.get("ok")),
                "name": db.get("database"),
                "user": db.get("user"),
                "tables": db.get("tables"),
                # Pool du conteneur API uniquement. Les pools des workers sont
                # exposés dans worker_runtime/details pour garder les processus isolés.
                "api_pools": pool_stats(),
            },
            "workers": {
                "campaign": campaign_worker,
                "outbound": outbound_worker,
                "inbound": inbound_worker,
                "batch": batch_worker,
                "segmentation": segmentation_worker,
                "attrition": attrition_worker,
                "digital_engagement": digital_engagement_worker,
                "best_channel": best_channel_worker,
                "commercial_pressure": commercial_pressure_worker,
            },
            "orchestration": {
                "worker": campaign_worker,
                "jobs": orchestration_stats(),
            },
            "outbound": {
                "workers": outbound_worker,
                "dispatches": outbound_stats(),
            },
            "inbound": {
                "workers": inbound_worker,
                "events": inbound_stats(),
            },
            "targeting": targeting_stats(),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "DATABASE_UNAVAILABLE",
                "message": str(exc),
            },
        ) from exc
