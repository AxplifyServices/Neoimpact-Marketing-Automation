from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, Optional

from app.orchestration.job_store import (
    claim_next_job,
    complete_job,
    fail_job,
    heartbeat_job,
    is_cancel_requested,
)

logger = logging.getLogger(__name__)

_WORKER_THREAD: Optional[threading.Thread] = None
_WORKER_STOP = threading.Event()
_WORKER_GUARD = threading.Lock()


def _job_heartbeat_loop(job_id: int, stop_event: threading.Event) -> None:
    interval = max(5.0, float(os.getenv("ORCHESTRATION_JOB_HEARTBEAT_SECONDS", "15") or "15"))
    while not stop_event.wait(timeout=interval):
        try:
            heartbeat_job(job_id)
        except Exception:
            logger.exception("Impossible de heartbeat le job d'orchestration id=%s", job_id)


def _process_job(job: Dict[str, Any]) -> None:
    job_id = int(job["id"])
    job_type = str(job.get("job_type") or "")
    id_campagne = str(job.get("id_campagne") or "").strip()

    if job_type != "CAMPAIGN_PREPARE" or not id_campagne:
        raise RuntimeError(f"Job d'orchestration non supporté: {job_type}")

    if is_cancel_requested(job_id):
        raise RuntimeError("job_cancelled")

    heartbeat_job(job_id, current=0, total=4, message="Préparation de la cible")

    from app.domain.campagne_service import prepare_campagne_execution

    prepare_campagne_execution(
        id_campagne,
        progress=lambda current, message: heartbeat_job(
            job_id,
            current=current,
            total=4,
            message=message,
        ),
        cancel_check=lambda: is_cancel_requested(job_id),
    )
    complete_job(job_id, message="Campagne prête")


def _worker_loop() -> None:
    idle = max(0.2, float(os.getenv("ORCHESTRATION_WORKER_IDLE_SECONDS", "0.5") or "0.5"))
    stale = max(60, int(os.getenv("ORCHESTRATION_JOB_STALE_SECONDS", "120") or "120"))

    while not _WORKER_STOP.is_set():
        try:
            job = claim_next_job(stale_after_seconds=stale)
            if job is None:
                _WORKER_STOP.wait(timeout=idle)
                continue
            heartbeat_stop = threading.Event()
            heartbeat_thread = threading.Thread(
                target=_job_heartbeat_loop,
                args=(int(job["id"]), heartbeat_stop),
                name=f"campaign-job-heartbeat-{job.get('id')}",
                daemon=True,
            )
            heartbeat_thread.start()
            try:
                _process_job(job)
                logger.info("Orchestration campagne terminée: job=%s campagne=%s", job.get("id"), job.get("id_campagne"))
            except Exception as exc:
                logger.exception("Échec orchestration: job=%s campagne=%s", job.get("id"), job.get("id_campagne"))
                status = fail_job(int(job["id"]), str(exc))
                if str(job.get("id_campagne") or "").strip():
                    from app.storage.campagnes_store_sqlite import set_execution_status
                    if status == "retry":
                        set_execution_status(str(job["id_campagne"]), "preparing", error=str(exc))
                    elif status == "cancelled":
                        set_execution_status(str(job["id_campagne"]), "cancelled", error=None)
                    else:
                        set_execution_status(str(job["id_campagne"]), "failed", error=str(exc))
            finally:
                heartbeat_stop.set()
                heartbeat_thread.join(timeout=2.0)
        except Exception:
            # Migration non appliquée, DB momentanément indisponible, etc.
            logger.exception("Worker d'orchestration momentanément indisponible")
            _WORKER_STOP.wait(timeout=5.0)


def start_orchestration_worker() -> Optional[threading.Thread]:
    global _WORKER_THREAD
    with _WORKER_GUARD:
        if _WORKER_THREAD is not None and _WORKER_THREAD.is_alive():
            return _WORKER_THREAD
        if str(os.getenv("ORCHESTRATION_WORKER_ENABLED", "true")).strip().lower() in {"0", "false", "no", "off"}:
            return None
        _WORKER_STOP.clear()
        _WORKER_THREAD = threading.Thread(
            target=_worker_loop,
            name="campaign-orchestration-worker",
            daemon=True,
        )
        _WORKER_THREAD.start()
        return _WORKER_THREAD


def stop_orchestration_worker() -> None:
    global _WORKER_THREAD
    with _WORKER_GUARD:
        _WORKER_STOP.set()
        thread = _WORKER_THREAD
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        _WORKER_THREAD = None


def orchestration_worker_status() -> Dict[str, Any]:
    thread = _WORKER_THREAD
    return {
        "enabled": str(os.getenv("ORCHESTRATION_WORKER_ENABLED", "true")).strip().lower() not in {"0", "false", "no", "off"},
        "running": bool(thread is not None and thread.is_alive()),
        "thread_name": thread.name if thread is not None else None,
    }
