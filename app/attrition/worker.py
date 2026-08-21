from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, time
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.attrition.engine import AttritionAlreadyRunningError, run_attrition_cycle

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "Africa/Casablanca"
DEFAULT_DAY = 1
DEFAULT_HOUR = 6
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


def get_attrition_worker_config() -> Dict[str, Any]:
    timezone_name = (os.getenv("ATTRITION_TIMEZONE", DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE)
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"ATTRITION_TIMEZONE inconnu : {timezone_name!r}") from exc

    return {
        "enabled": _env_bool("ATTRITION_WORKER_ENABLED", True),
        "run_on_start": _env_bool("ATTRITION_RUN_ON_START", True),
        "timezone_name": timezone_name,
        "timezone": timezone,
        "day": _env_int("ATTRITION_MONTHLY_DAY", DEFAULT_DAY, 1, 28),
        "hour": _env_int("ATTRITION_MONTHLY_HOUR", DEFAULT_HOUR, 0, 23),
        "minute": _env_int("ATTRITION_MONTHLY_MINUTE", DEFAULT_MINUTE, 0, 59),
    }


def _next_monthly_run(now: datetime, *, timezone: ZoneInfo, day: int, hour: int, minute: int) -> datetime:
    candidate = datetime(now.year, now.month, day, hour, minute, tzinfo=timezone)
    if candidate > now:
        return candidate
    if now.month == 12:
        return datetime(now.year + 1, 1, day, hour, minute, tzinfo=timezone)
    return datetime(now.year, now.month + 1, day, hour, minute, tzinfo=timezone)


def _run_once(trigger: str) -> None:
    global _LAST_RUN, _LAST_ERROR
    try:
        result = run_attrition_cycle()
        result["trigger"] = trigger
        with _STATUS_LOCK:
            _LAST_RUN = result
            _LAST_ERROR = None
        logger.info("Attrition terminée (%s): %s", trigger, result)
    except AttritionAlreadyRunningError as exc:
        logger.warning("Attrition ignorée (%s): %s", trigger, exc)
    except Exception as exc:
        with _STATUS_LOCK:
            _LAST_ERROR = str(exc)
        logger.exception("Échec attrition (%s)", trigger)


def _loop() -> None:
    global _NEXT_RUN
    config = get_attrition_worker_config()
    timezone: ZoneInfo = config["timezone"]

    if bool(config["run_on_start"]) and not _STOP.is_set():
        _run_once("startup")

    while not _STOP.is_set():
        now = datetime.now(timezone)
        target = _next_monthly_run(
            now,
            timezone=timezone,
            day=int(config["day"]),
            hour=int(config["hour"]),
            minute=int(config["minute"]),
        )
        with _STATUS_LOCK:
            _NEXT_RUN = target

        while not _STOP.is_set():
            remaining = target.timestamp() - datetime.now(timezone).timestamp()
            if remaining <= 0:
                break
            _STOP.wait(timeout=min(remaining, 60.0))

        if _STOP.is_set():
            break
        _run_once("scheduled_monthly")

    with _STATUS_LOCK:
        _NEXT_RUN = None


def start_attrition_worker() -> List[threading.Thread]:
    global _THREADS
    with _GUARD:
        if any(thread.is_alive() for thread in _THREADS):
            return list(_THREADS)

        config = get_attrition_worker_config()
        if not bool(config["enabled"]):
            logger.info("Worker attrition désactivé par configuration.")
            _THREADS = []
            return []

        _STOP.clear()
        thread = threading.Thread(target=_loop, name="attrition-monthly-worker", daemon=True)
        thread.start()
        _THREADS = [thread]
        return list(_THREADS)


def stop_attrition_worker() -> None:
    global _THREADS
    with _GUARD:
        _STOP.set()
        threads = list(_THREADS)
        _THREADS = []
    for thread in threads:
        if thread.is_alive():
            thread.join(timeout=5.0)


def attrition_worker_status() -> Dict[str, Any]:
    with _STATUS_LOCK:
        next_run = _NEXT_RUN.isoformat() if _NEXT_RUN is not None else None
        last_run = dict(_LAST_RUN)
        last_error = _LAST_ERROR
    config = get_attrition_worker_config()
    return {
        "enabled": bool(config["enabled"]),
        "running": any(thread.is_alive() for thread in _THREADS),
        "run_on_start": bool(config["run_on_start"]),
        "timezone": config["timezone_name"],
        "day": int(config["day"]),
        "hour": int(config["hour"]),
        "minute": int(config["minute"]),
        "next_run_time": next_run,
        "last_run": last_run,
        "last_error": last_error,
    }
