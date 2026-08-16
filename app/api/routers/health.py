from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.storage.postgres_db import healthcheck as postgres_healthcheck

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
