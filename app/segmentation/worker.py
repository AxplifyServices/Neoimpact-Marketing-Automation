from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.segmentation.engine import (
    SegmentationAlreadyRunningError,
    SegmentationDataNotReadyError,
    run_segmentation_cycle,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "Africa/Casablanca"
DEFAULT_HOUR = 5
DEFAULT_MINUTE = 0

_STOP = threading.Event()
_GUARD = threading.Lock()
_THREADS: List[threading.Thread] = []
_STATUS_LOCK = threading.Lock()
_NEXT_RUN: Optional[datetime] = None
_LAST_RUN: Dict[str, Any] = {}
_LAST_ERROR: Optional[str] = None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "non", "off"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise RuntimeError(f"{name} doit être un entier, reçu : {raw!r}") from exc
    if value < minimum or value > maximum:
        raise RuntimeError(f"{name} doit être entre {minimum} et {maximum}.")
    return value


def get_segmentation_worker_config() -> Dict[str, Any]:
    timezone_name = (os.getenv("SEGMENTATION_TIMEZONE", DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE)
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"SEGMENTATION_TIMEZONE inconnu : {timezone_name!r}") from exc

    return {
        "enabled": _env_bool("SEGMENTATION_WORKER_ENABLED", True),
        "run_on_start": _env_bool("SEGMENTATION_RUN_ON_START", True),
        "timezone_name": timezone_name,
        "timezone": timezone,
        "hour": _env_int("SEGMENTATION_DAILY_HOUR", DEFAULT_HOUR, 0, 23),
        "minute": _env_int("SEGMENTATION_DAILY_MINUTE", DEFAULT_MINUTE, 0, 59),
    }


def _next_daily_run(now: datetime, *, timezone: ZoneInfo, hour: int, minute: int) -> datetime:
    candidate = datetime.combine(now.date(), time(hour=hour, minute=minute), tzinfo=timezone)
    if candidate <= now:
        candidate = datetime.combine(
            now.date() + timedelta(days=1),
            time(hour=hour, minute=minute),
            tzinfo=timezone,
        )
    return candidate


def _run_once(trigger: str) -> None:
    global _LAST_RUN, _LAST_ERROR
    try:
        result = run_segmentation_cycle()
        result["trigger"] = trigger
        with _STATUS_LOCK:
            _LAST_RUN = result
            _LAST_ERROR = None
        logger.info("Segmentation terminée (%s): %s", trigger, result)
    except SegmentationAlreadyRunningError as exc:
        logger.warning("Segmentation ignorée (%s): %s", trigger, exc)
    except SegmentationDataNotReadyError as exc:
        # Le worker reste vivant : lorsque le datamart mensuel sera alimenté,
        # le prochain passage quotidien pourra reprendre automatiquement.
        with _STATUS_LOCK:
            _LAST_ERROR = str(exc)
        logger.error("Segmentation non exécutée (%s): %s", trigger, exc)
    except Exception as exc:
        with _STATUS_LOCK:
            _LAST_ERROR = str(exc)
        logger.exception("Échec segmentation (%s)", trigger)


def _loop() -> None:
    global _NEXT_RUN
    config = get_segmentation_worker_config()
    timezone: ZoneInfo = config["timezone"]

    if bool(config["run_on_start"]) and not _STOP.is_set():
        _run_once("startup")

    while not _STOP.is_set():
        now = datetime.now(timezone)
        target = _next_daily_run(
            now,
            timezone=timezone,
            hour=int(config["hour"]),
            minute=int(config["minute"]),
        )
        with _STATUS_LOCK:
            _NEXT_RUN = target

        while not _STOP.is_set():
            now = datetime.now(timezone)
            remaining = target.timestamp() - now.timestamp()
            if remaining <= 0:
                break
            _STOP.wait(timeout=min(remaining, 60.0))

        if _STOP.is_set():
            break
        _run_once("scheduled_daily")

    with _STATUS_LOCK:
        _NEXT_RUN = None


def start_segmentation_worker() -> List[threading.Thread]:
    global _THREADS
    with _GUARD:
        if any(thread.is_alive() for thread in _THREADS):
            return list(_THREADS)

        config = get_segmentation_worker_config()
        if not bool(config["enabled"]):
            logger.info("Worker segmentation désactivé par configuration.")
            _THREADS = []
            return []

        _STOP.clear()
        thread = threading.Thread(
            target=_loop,
            name="segmentation-daily-worker",
            daemon=True,
        )
        thread.start()
        _THREADS = [thread]
        return list(_THREADS)


def stop_segmentation_worker() -> None:
    global _THREADS
    with _GUARD:
        _STOP.set()
        threads = list(_THREADS)
        _THREADS = []
    for thread in threads:
        if thread.is_alive():
            thread.join(timeout=5.0)


def segmentation_worker_status() -> Dict[str, Any]:
    with _STATUS_LOCK:
        next_run = _NEXT_RUN.isoformat() if _NEXT_RUN is not None else None
        last_run = dict(_LAST_RUN)
        last_error = _LAST_ERROR
    config = get_segmentation_worker_config()
    return {
        "enabled": bool(config["enabled"]),
        "running": any(thread.is_alive() for thread in _THREADS),
        "run_on_start": bool(config["run_on_start"]),
        "timezone": config["timezone_name"],
        "hour": int(config["hour"]),
        "minute": int(config["minute"]),
        "next_run_time": next_run,
        "last_run": last_run,
        "last_error": last_error,
    }
