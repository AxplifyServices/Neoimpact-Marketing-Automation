from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from typing import Any, Callable, Dict, Tuple

from app.storage.postgres_db import close_pools, pool_stats
from app.workers.runtime import heartbeat_worker, register_worker, stop_worker

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

_STOP = threading.Event()


def _signal_handler(signum: int, _frame: Any) -> None:
    logger.info("Signal %s reçu : arrêt demandé", signum)
    _STOP.set()


def _campaign_spec() -> Tuple[Callable[[], Any], Callable[[], None], Callable[[], Dict[str, Any]], Callable[[Dict[str, Any]], bool]]:
    from app.orchestration.campaign_worker import (
        orchestration_worker_status,
        start_orchestration_worker,
        stop_orchestration_worker,
    )
    return (
        start_orchestration_worker,
        stop_orchestration_worker,
        orchestration_worker_status,
        lambda status: bool(status.get("running")),
    )


def _outbound_spec() -> Tuple[Callable[[], Any], Callable[[], None], Callable[[], Dict[str, Any]], Callable[[Dict[str, Any]], bool]]:
    from app.outbound.worker import start_outbound_workers, stop_outbound_workers, worker_status
    return (
        start_outbound_workers,
        stop_outbound_workers,
        worker_status,
        lambda status: bool(status.get("producer_running"))
        and int((status.get("running") or {}).get("MAIL") or 0) > 0
        and int((status.get("running") or {}).get("TERRAIN") or 0) > 0,
    )


def _inbound_spec() -> Tuple[Callable[[], Any], Callable[[], None], Callable[[], Dict[str, Any]], Callable[[Dict[str, Any]], bool]]:
    from app.inbound.worker import start_inbound_workers, stop_inbound_workers, worker_status
    return (
        start_inbound_workers,
        stop_inbound_workers,
        worker_status,
        lambda status: int(status.get("running") or 0) > 0,
    )


def _batch_spec() -> Tuple[Callable[[], Any], Callable[[], None], Callable[[], Dict[str, Any]], Callable[[Dict[str, Any]], bool]]:
    from app.batch.worker import batch_worker_status, start_batch_worker, stop_batch_worker
    def healthy(status: Dict[str, Any]) -> bool:
        schedule = status.get("schedule") or {}
        schedule_ok = not bool(schedule.get("enabled")) or bool(schedule.get("running"))
        return bool(status.get("manual_consumer_running")) and schedule_ok

    return (
        start_batch_worker,
        stop_batch_worker,
        batch_worker_status,
        healthy,
    )



def _segmentation_spec() -> Tuple[Callable[[], Any], Callable[[], None], Callable[[], Dict[str, Any]], Callable[[Dict[str, Any]], bool]]:
    from app.segmentation.worker import (
        segmentation_worker_status,
        start_segmentation_worker,
        stop_segmentation_worker,
    )
    return (
        start_segmentation_worker,
        stop_segmentation_worker,
        segmentation_worker_status,
        lambda status: not bool(status.get("enabled")) or bool(status.get("running")),
    )



def _attrition_spec() -> Tuple[Callable[[], Any], Callable[[], None], Callable[[], Dict[str, Any]], Callable[[Dict[str, Any]], bool]]:
    from app.attrition.worker import (
        attrition_worker_status,
        start_attrition_worker,
        stop_attrition_worker,
    )
    return (
        start_attrition_worker,
        stop_attrition_worker,
        attrition_worker_status,
        lambda status: not bool(status.get("enabled")) or bool(status.get("running")),
    )

def _spec(role: str):
    specs = {
        "campaign": _campaign_spec,
        "outbound": _outbound_spec,
        "inbound": _inbound_spec,
        "batch": _batch_spec,
        "segmentation": _segmentation_spec,
        "attrition": _attrition_spec,
    }
    factory = specs.get(role)
    if factory is None:
        raise ValueError(f"Worker inconnu: {role}")
    return factory()


def main() -> int:
    role = str(sys.argv[1] if len(sys.argv) > 1 else os.getenv("WORKER_ROLE") or "").strip().lower()
    if not role:
        print("usage: python -m app.workers.runner <campaign|outbound|inbound|batch|segmentation|attrition>", file=sys.stderr)
        return 2

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    start, stop, status_fn, healthy_fn = _spec(role)
    heartbeat_seconds = max(2.0, float(os.getenv("WORKER_HEARTBEAT_SECONDS", "5") or "5"))
    runtime_error: str | None = None

    try:
        register_worker(role, status="starting", details={"role": role})
        start()
        logger.info("Worker %s démarré", role)

        while not _STOP.is_set():
            status = status_fn()
            details = dict(status)
            details["postgres_pools"] = pool_stats()
            if not healthy_fn(status):
                runtime_error = f"worker_internal_thread_stopped: {status}"
                heartbeat_worker(role, status="error", details=details, error=runtime_error)
                logger.error(runtime_error)
                return 1
            heartbeat_worker(role, status="running", details=details)
            _STOP.wait(timeout=heartbeat_seconds)

        return 0
    except Exception as exc:
        runtime_error = str(exc)
        logger.exception("Worker %s arrêté sur erreur", role)
        try:
            heartbeat_worker(role, status="error", details={"role": role}, error=runtime_error)
        except Exception:
            pass
        return 1
    finally:
        try:
            stop()
        except Exception:
            logger.exception("Erreur pendant l'arrêt du worker %s", role)
        try:
            stop_worker(role, error=runtime_error)
        except Exception:
            logger.exception("Impossible d'enregistrer l'arrêt du worker %s", role)
        close_pools()


if __name__ == "__main__":
    raise SystemExit(main())
