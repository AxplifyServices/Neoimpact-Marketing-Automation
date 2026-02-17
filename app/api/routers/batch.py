# app/api/routers/batch.py
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from app.scripts.batch_manuel import run_batch_manuel

router = APIRouter()


@router.post("/batch/run")
def run_batch(
    limit: int = Query(default=0, ge=0),
    dry_run: bool = Query(default=False),
) -> Dict[str, Any]:
    """
    Compat front:
    - garde /batch/run
    - renvoie toujours {"ok": True/False, "result": ...}

    Ajouts non cassants:
    - limit (0 => pas de limite)
    - dry_run (false par défaut)

    Compat back:
    - si run_batch_manuel() ne supporte pas (limit, dry_run), fallback automatique.
    """
    try:
        # NEW (si ta fonction accepte des params)
        try:
            res = run_batch_manuel(limit=limit, dry_run=dry_run)
        except TypeError:
            # compat: ancienne signature
            res = run_batch_manuel()

        return {"ok": True, "result": res}

    except Exception as e:
        # Ne jamais exposer une stacktrace au front, on renvoie une 500 propre
        raise HTTPException(
            status_code=500,
            detail={"error": "BATCH_RUN_FAILED", "message": str(e)},
        )
