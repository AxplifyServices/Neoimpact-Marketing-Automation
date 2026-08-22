from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.product_scoring.engine import ProductScoringAlreadyRunningError, run_product_scoring_cycle

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
    return default if raw is None else raw.strip().lower() not in {"0","false","no","non","off"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    value = default if raw is None or not raw.strip() else int(raw.strip())
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} doit être entre {minimum} et {maximum}.")
    return value


def get_product_scoring_worker_config() -> Dict[str, Any]:
    timezone_name = os.getenv("PRODUCT_SCORING_TIMEZONE", DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"PRODUCT_SCORING_TIMEZONE inconnu: {timezone_name}") from exc
    return {
        "enabled": _env_bool("PRODUCT_SCORING_WORKER_ENABLED", True),
        "run_on_start": _env_bool("PRODUCT_SCORING_RUN_ON_START", True),
        "timezone_name": timezone_name, "timezone": timezone,
        "day": _env_int("PRODUCT_SCORING_MONTHLY_DAY", 1, 1, 28),
        "hour": _env_int("PRODUCT_SCORING_MONTHLY_HOUR", 7, 0, 23),
        "minute": _env_int("PRODUCT_SCORING_MONTHLY_MINUTE", 0, 0, 59),
    }


def _next_monthly(now: datetime, cfg: Dict[str, Any]) -> datetime:
    target = datetime(now.year, now.month, cfg["day"], cfg["hour"], cfg["minute"], tzinfo=cfg["timezone"])
    if target > now:
        return target
    if now.month == 12:
        return datetime(now.year+1, 1, cfg["day"], cfg["hour"], cfg["minute"], tzinfo=cfg["timezone"])
    return datetime(now.year, now.month+1, cfg["day"], cfg["hour"], cfg["minute"], tzinfo=cfg["timezone"])


def _run_once(trigger: str):
    global _LAST_RUN, _LAST_ERROR
    try:
        result = run_product_scoring_cycle(trigger=trigger)
        with _STATUS_LOCK:
            _LAST_RUN, _LAST_ERROR = result, None
        logger.info("Appétences produits terminées (%s): %s", trigger, result)
        return result
    except ProductScoringAlreadyRunningError as exc:
        logger.warning("Scoring produits ignoré: %s", exc)
    except Exception as exc:
        with _STATUS_LOCK:
            _LAST_ERROR = str(exc)
        logger.exception("Échec scoring produits (%s)", trigger)
    return None


def _loop() -> None:
    global _NEXT_RUN
    cfg = get_product_scoring_worker_config()
    if cfg["run_on_start"] and not _STOP.is_set():
        _run_once("startup")
    while not _STOP.is_set():
        now = datetime.now(cfg["timezone"])
        target = _next_monthly(now, cfg)
        with _STATUS_LOCK:
            _NEXT_RUN = target
        while not _STOP.is_set():
            remaining = target.timestamp() - datetime.now(cfg["timezone"]).timestamp()
            if remaining <= 0:
                break
            _STOP.wait(timeout=min(remaining, 60.0))
        if not _STOP.is_set():
            _run_once("scheduled_monthly")
    with _STATUS_LOCK:
        _NEXT_RUN = None


def start_product_scoring_worker() -> List[threading.Thread]:
    global _THREADS
    with _GUARD:
        if any(t.is_alive() for t in _THREADS):
            return list(_THREADS)
        cfg = get_product_scoring_worker_config()
        if not cfg["enabled"]:
            _THREADS = []
            return []
        _STOP.clear()
        t = threading.Thread(target=_loop, name="product-scoring-monthly-worker", daemon=True)
        t.start(); _THREADS = [t]
        return list(_THREADS)


def stop_product_scoring_worker() -> None:
    global _THREADS
    with _GUARD:
        _STOP.set(); threads=list(_THREADS); _THREADS=[]
    for t in threads:
        if t.is_alive(): t.join(timeout=5.0)


def product_scoring_worker_status() -> Dict[str, Any]:
    with _STATUS_LOCK:
        next_run = _NEXT_RUN.isoformat() if _NEXT_RUN else None
        last_run = dict(_LAST_RUN); last_error = _LAST_ERROR
    cfg = get_product_scoring_worker_config()
    return {
        "enabled": cfg["enabled"], "running": any(t.is_alive() for t in _THREADS),
        "run_on_start": cfg["run_on_start"], "timezone": cfg["timezone_name"],
        "day": cfg["day"], "hour": cfg["hour"], "minute": cfg["minute"],
        "next_run_time": next_run, "last_run": last_run, "last_error": last_error,
    }
