from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from app.batch.batch_runner import BatchAlreadyRunningError, run_batch_with_lock
from app.batch.scheduler import get_batch_scheduler_status

router = APIRouter()

_manual_guard = threading.Lock()
_manual_thread: threading.Thread | None = None
_manual_state: Dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "ok": None,
    "error": None,
    "result": None,
}


def _run_manual_background() -> None:
    global _manual_state
    try:
        execution = run_batch_with_lock(trigger="manual_api")
        with _manual_guard:
            _manual_state.update(
                running=False,
                finished_at=datetime.now().isoformat(timespec="seconds"),
                ok=True,
                error=None,
                result=execution.get("result"),
            )
    except BatchAlreadyRunningError as exc:
        with _manual_guard:
            _manual_state.update(
                running=False,
                finished_at=datetime.now().isoformat(timespec="seconds"),
                ok=False,
                error=str(exc),
                result=None,
            )
    except Exception as exc:
        with _manual_guard:
            _manual_state.update(
                running=False,
                finished_at=datetime.now().isoformat(timespec="seconds"),
                ok=False,
                error=str(exc),
                result=None,
            )


@router.post("/batch/run")
def run_batch(
    limit: int = Query(default=0, ge=0),
    dry_run: bool = Query(default=False),
) -> Dict[str, Any]:
    """Démarre le batch manuel en arrière-plan afin de ne jamais bloquer HTTP/Traefik."""
    global _manual_thread, _manual_state
    _ = limit, dry_run

    with _manual_guard:
        if _manual_thread is not None and _manual_thread.is_alive():
            raise HTTPException(
                status_code=409,
                detail={"error": "BATCH_ALREADY_RUNNING", "message": "Le batch manuel est déjà en cours."},
            )

        _manual_state = {
            "running": True,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
            "ok": None,
            "error": None,
            "result": None,
        }
        _manual_thread = threading.Thread(
            target=_run_manual_background,
            name="manual-batch",
            daemon=True,
        )
        _manual_thread.start()

    return {"ok": True, "started": True, "message": "Batch lancé en arrière-plan."}


@router.get("/batch/status")
def batch_status() -> Dict[str, Any]:
    with _manual_guard:
        state = dict(_manual_state)
    return {"ok": True, "manual": state, "schedule": get_batch_scheduler_status()}


@router.get("/batch/schedule")
def batch_schedule() -> Dict[str, Any]:
    return {"ok": True, "schedule": get_batch_scheduler_status()}
