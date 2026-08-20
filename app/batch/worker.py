from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List

from app.batch.batch_runner import BatchAlreadyRunningError, run_batch_with_lock
from app.batch.request_store import (
    claim_next_request,
    complete_request,
    fail_request,
    heartbeat_request,
    latest_request,
    requeue_request,
)
from app.batch.scheduler import get_batch_scheduler_status, start_batch_scheduler, stop_batch_scheduler
from app.workers.runtime import instance_id

logger = logging.getLogger(__name__)

_STOP = threading.Event()
_GUARD = threading.Lock()
_THREADS: List[threading.Thread] = []


def _request_heartbeat_loop(request_id: int, worker_id: str, stop_event: threading.Event) -> None:
    interval = max(5.0, float(os.getenv("BATCH_REQUEST_HEARTBEAT_SECONDS", "15") or "15"))
    while not stop_event.wait(timeout=interval):
        try:
            heartbeat_request(request_id, worker_id=worker_id)
        except Exception:
            logger.exception("Impossible de heartbeat la demande batch id=%s", request_id)


def _manual_request_loop() -> None:
    idle = max(0.5, float(os.getenv("BATCH_REQUEST_IDLE_SECONDS", "1") or "1"))
    stale = max(60, int(os.getenv("BATCH_REQUEST_STALE_SECONDS", "120") or "120"))
    worker_id = instance_id()

    while not _STOP.is_set():
        try:
            request = claim_next_request(worker_id=worker_id, stale_seconds=stale)
            if request is None:
                _STOP.wait(timeout=idle)
                continue

            request_id = int(request["id"])
            heartbeat_stop = threading.Event()
            heartbeat_thread = threading.Thread(
                target=_request_heartbeat_loop,
                args=(request_id, worker_id, heartbeat_stop),
                name=f"batch-request-heartbeat-{request_id}",
                daemon=True,
            )
            heartbeat_thread.start()
            try:
                execution = run_batch_with_lock(trigger=str(request.get("trigger") or "manual_api"))
                complete_request(request_id, execution)
            except BatchAlreadyRunningError as exc:
                # Le scheduler peut avoir démarré quelques millisecondes avant la
                # requête manuelle : on la garde et on réessaie ensuite.
                requeue_request(request_id, delay_seconds=30, error=str(exc))
            except Exception as exc:
                logger.exception("Échec demande batch id=%s", request_id)
                fail_request(request_id, str(exc))
            finally:
                heartbeat_stop.set()
                heartbeat_thread.join(timeout=2.0)
        except Exception:
            logger.exception("Batch request consumer momentanément indisponible")
            _STOP.wait(timeout=5.0)


def start_batch_worker() -> List[threading.Thread]:
    global _THREADS
    with _GUARD:
        if any(thread.is_alive() for thread in _THREADS):
            return list(_THREADS)
        _STOP.clear()
        threads: List[threading.Thread] = []

        scheduler_thread = start_batch_scheduler()
        if scheduler_thread is not None:
            threads.append(scheduler_thread)

        manual_thread = threading.Thread(
            target=_manual_request_loop,
            name="batch-manual-request-consumer",
            daemon=True,
        )
        manual_thread.start()
        threads.append(manual_thread)
        _THREADS = threads
        return list(_THREADS)


def stop_batch_worker() -> None:
    global _THREADS
    with _GUARD:
        _STOP.set()
        threads = list(_THREADS)
        _THREADS = []
    stop_batch_scheduler()
    for thread in threads:
        if thread.is_alive():
            thread.join(timeout=5.0)


def batch_worker_status() -> Dict[str, Any]:
    names = [thread.name for thread in _THREADS if thread.is_alive()]
    return {
        "manual_consumer_running": "batch-manual-request-consumer" in names,
        "schedule": get_batch_scheduler_status(),
        "latest_request": latest_request(),
    }
