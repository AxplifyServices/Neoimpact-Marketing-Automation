from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.commercial_pressure.engine import (
    CommercialPressureAlreadyRunningError,
    run_commercial_pressure_cycle,
)

logger = logging.getLogger(__name__)
DEFAULT_TIMEZONE = "Africa/Casablanca"
DEFAULT_DAY = 1
DEFAULT_HOUR = 2
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
    value = int(raw.strip())
    if value < minimum or value > maximum:
        raise RuntimeError(f"{name} doit être entre {minimum} et {maximum}.")
    return value


def get_commercial_pressure_worker_config() -> Dict[str, Any]:
    timezone_name = os.getenv("COMMERCIAL_PRESSURE_TIMEZONE", DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"COMMERCIAL_PRESSURE_TIMEZONE inconnu : {timezone_name!r}") from exc
    return {
        "enabled": _env_bool("COMMERCIAL_PRESSURE_WORKER_ENABLED", True),
        "run_on_start": _env_bool("COMMERCIAL_PRESSURE_RUN_ON_START", True),
        "timezone_name": timezone_name,
        "timezone": timezone,
        "day": _env_int("COMMERCIAL_PRESSURE_MONTHLY_DAY", DEFAULT_DAY, 1, 28),
        "hour": _env_int("COMMERCIAL_PRESSURE_MONTHLY_HOUR", DEFAULT_HOUR, 0, 23),
        "minute": _env_int("COMMERCIAL_PRESSURE_MONTHLY_MINUTE", DEFAULT_MINUTE, 0, 59),
    }


def _next_monthly_run(now: datetime, *, timezone: ZoneInfo, day: int, hour: int, minute: int) -> datetime:
    candidate = datetime(now.year, now.month, day, hour, minute, tzinfo=timezone)
    if candidate > now:
        return candidate
    if now.month == 12:
        return datetime(now.year + 1, 1, day, hour, minute, tzinfo=timezone)
    return datetime(now.year, now.month + 1, day, hour, minute, tzinfo=timezone)


def _run_once(trigger: str) -> Dict[str, Any] | None:
    global _LAST_RUN, _LAST_ERROR
    try:
        result = run_commercial_pressure_cycle(trigger=trigger)
        with _STATUS_LOCK:
            _LAST_RUN = result
            _LAST_ERROR = None
        logger.info("Pression commerciale terminée (%s): %s", trigger, result)
        return result
    except CommercialPressureAlreadyRunningError as exc:
        logger.warning("Pression commerciale ignorée (%s): %s", trigger, exc)
        return None
    except Exception as exc:
        with _STATUS_LOCK:
            _LAST_ERROR = str(exc)
        logger.exception("Échec pression commerciale (%s)", trigger)
        return None


def _loop() -> None:
    global _NEXT_RUN
    config = get_commercial_pressure_worker_config()
    timezone: ZoneInfo = config["timezone"]

    if bool(config["run_on_start"]) and not _STOP.is_set():
        startup_result = _run_once("startup")
        # Sur une base neuve, Best Channel peut encore être en train de créer
        # son historique fake. On réessaie sans attendre le mois suivant.
        retries = 0
        while (
            startup_result
            and startup_result.get("reason") == "waiting_for_best_channel_history"
            and not _STOP.is_set()
            and retries < 10
        ):
            retries += 1
            logger.info("Historique Best Channel pas encore prêt; nouveau contrôle dans 120 s (%s/10).", retries)
            _STOP.wait(timeout=120.0)
            if not _STOP.is_set():
                startup_result = _run_once(f"startup_retry_{retries}")

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


def start_commercial_pressure_worker() -> List[threading.Thread]:
    global _THREADS
    with _GUARD:
        if any(thread.is_alive() for thread in _THREADS):
            return list(_THREADS)
        config = get_commercial_pressure_worker_config()
        if not bool(config["enabled"]):
            logger.info("Worker pression commerciale désactivé.")
            _THREADS = []
            return []
        _STOP.clear()
        thread = threading.Thread(target=_loop, name="commercial-pressure-monthly-worker", daemon=True)
        thread.start()
        _THREADS = [thread]
        return list(_THREADS)


def stop_commercial_pressure_worker() -> None:
    global _THREADS
    with _GUARD:
        _STOP.set()
        threads = list(_THREADS)
        _THREADS = []
    for thread in threads:
        if thread.is_alive():
            thread.join(timeout=5.0)


def commercial_pressure_worker_status() -> Dict[str, Any]:
    with _STATUS_LOCK:
        next_run = _NEXT_RUN.isoformat() if _NEXT_RUN is not None else None
        last_run = dict(_LAST_RUN)
        last_error = _LAST_ERROR
    config = get_commercial_pressure_worker_config()
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
