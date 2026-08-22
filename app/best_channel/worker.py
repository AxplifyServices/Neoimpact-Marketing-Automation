from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from app.best_channel.engine import BestChannelAlreadyRunningError, run_best_channel_cycle

logger = logging.getLogger(__name__)
DEFAULT_TIMEZONE = "Africa/Casablanca"
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


def get_best_channel_worker_config() -> Dict[str, Any]:
    tz_name = os.getenv("BEST_CHANNEL_TIMEZONE", DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE
    return {
        "enabled": _env_bool("BEST_CHANNEL_WORKER_ENABLED", True),
        "run_on_start": _env_bool("BEST_CHANNEL_RUN_ON_START", True),
        "timezone_name": tz_name,
        "timezone": ZoneInfo(tz_name),
        "hour": max(0, min(23, int(os.getenv("BEST_CHANNEL_DAILY_HOUR", "3") or "3"))),
        "minute": max(0, min(59, int(os.getenv("BEST_CHANNEL_DAILY_MINUTE", "0") or "0"))),
    }


def _next_daily_run(now: datetime, *, hour: int, minute: int) -> datetime:
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def _run_once(trigger: str) -> None:
    global _LAST_RUN, _LAST_ERROR
    try:
        result = run_best_channel_cycle(trigger=trigger)
        with _STATUS_LOCK:
            _LAST_RUN = dict(result)
            _LAST_ERROR = None
        logger.info("Best Channel terminé (%s): %s", trigger, result)
    except BestChannelAlreadyRunningError as exc:
        logger.info("Best Channel ignoré (%s): %s", trigger, exc)
    except Exception as exc:
        with _STATUS_LOCK:
            _LAST_ERROR = str(exc)
        logger.exception("Échec Best Channel (%s)", trigger)


def _loop() -> None:
    global _NEXT_RUN
    config = get_best_channel_worker_config()
    tz = config["timezone"]
    if config["run_on_start"] and not _STOP.is_set():
        _run_once("startup")
    while not _STOP.is_set():
        now = datetime.now(tz)
        target = _next_daily_run(now, hour=config["hour"], minute=config["minute"])
        with _STATUS_LOCK:
            _NEXT_RUN = target
        while not _STOP.is_set():
            remaining = target.timestamp() - datetime.now(tz).timestamp()
            if remaining <= 0:
                break
            _STOP.wait(timeout=min(remaining, 60.0))
        if not _STOP.is_set():
            _run_once("scheduled_daily")
    with _STATUS_LOCK:
        _NEXT_RUN = None


def start_best_channel_worker() -> List[threading.Thread]:
    global _THREADS
    with _GUARD:
        if any(t.is_alive() for t in _THREADS):
            return list(_THREADS)
        config = get_best_channel_worker_config()
        if not config["enabled"]:
            _THREADS = []
            return []
        _STOP.clear()
        thread = threading.Thread(target=_loop, name="best-channel-daily-worker", daemon=True)
        thread.start()
        _THREADS = [thread]
        return list(_THREADS)


def stop_best_channel_worker() -> None:
    global _THREADS
    with _GUARD:
        _STOP.set()
        threads = list(_THREADS)
        _THREADS = []
    for thread in threads:
        if thread.is_alive():
            thread.join(timeout=5.0)


def best_channel_worker_status() -> Dict[str, Any]:
    with _STATUS_LOCK:
        next_run = _NEXT_RUN.isoformat() if _NEXT_RUN else None
        last_run = dict(_LAST_RUN)
        last_error = _LAST_ERROR
    config = get_best_channel_worker_config()
    return {
        "enabled": config["enabled"],
        "running": any(t.is_alive() for t in _THREADS),
        "run_on_start": config["run_on_start"],
        "timezone": config["timezone_name"],
        "hour": config["hour"],
        "minute": config["minute"],
        "next_run_time": next_run,
        "last_run": last_run,
        "last_error": last_error,
    }
