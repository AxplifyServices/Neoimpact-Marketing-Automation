from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, time, timedelta
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "Africa/Casablanca"
DEFAULT_HOUR = 4
DEFAULT_MINUTE = 0

_scheduler_thread: Optional[threading.Thread] = None
_scheduler_stop = threading.Event()
_scheduler_guard = threading.Lock()
_next_run_time: Optional[datetime] = None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default

    return raw.strip().lower() not in {
        "0",
        "false",
        "no",
        "non",
        "off",
    }


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default

    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise RuntimeError(
            f"La variable {name} doit être un entier, valeur reçue : {raw!r}."
        ) from exc

    if value < minimum or value > maximum:
        raise RuntimeError(
            f"La variable {name} doit être comprise entre {minimum} et {maximum}."
        )

    return value


def get_scheduler_config() -> Dict[str, Any]:
    timezone_name = (
        os.getenv("BATCH_TIMEZONE", DEFAULT_TIMEZONE).strip()
        or DEFAULT_TIMEZONE
    )

    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(
            f"Fuseau horaire BATCH_TIMEZONE inconnu : {timezone_name!r}."
        ) from exc

    return {
        "enabled": _env_bool("BATCH_DAILY_ENABLED", True),
        "timezone_name": timezone_name,
        "timezone": timezone,
        "hour": _env_int("BATCH_DAILY_HOUR", DEFAULT_HOUR, 0, 23),
        "minute": _env_int("BATCH_DAILY_MINUTE", DEFAULT_MINUTE, 0, 59),
    }


def _compute_next_run(
    *,
    now: datetime,
    timezone: ZoneInfo,
    hour: int,
    minute: int,
) -> datetime:
    candidate = datetime.combine(
        now.date(),
        time(hour=hour, minute=minute),
        tzinfo=timezone,
    )

    if candidate <= now:
        candidate = datetime.combine(
            now.date() + timedelta(days=1),
            time(hour=hour, minute=minute),
            tzinfo=timezone,
        )

    return candidate


def _run_daily_batch() -> None:
    from app.batch.batch_runner import (
        BatchAlreadyRunningError,
        run_batch_with_lock,
    )

    try:
        run_batch_with_lock(trigger="scheduled_daily")
    except BatchAlreadyRunningError:
        logger.warning(
            "Batch quotidien ignoré : une autre exécution est déjà en cours."
        )
    except Exception:
        # L'échec d'une journée ne tue pas le scheduler : le lendemain reste planifié.
        logger.exception("Échec de l'exécution automatique quotidienne du batch.")


def _scheduler_loop() -> None:
    global _next_run_time

    config = get_scheduler_config()
    timezone: ZoneInfo = config["timezone"]
    hour = int(config["hour"])
    minute = int(config["minute"])

    target = _compute_next_run(
        now=datetime.now(timezone),
        timezone=timezone,
        hour=hour,
        minute=minute,
    )
    _next_run_time = target

    logger.info(
        "Scheduler batch activé : %02d:%02d (%s), prochaine exécution : %s",
        hour,
        minute,
        config["timezone_name"],
        target.isoformat(),
    )

    while not _scheduler_stop.is_set():
        now = datetime.now(timezone)
        seconds_until_target = target.timestamp() - now.timestamp()

        if seconds_until_target > 0:
            # Réveil au plus chaque minute pour rester robuste aux changements
            # d'heure/fuseau et aux ajustements de l'horloge système.
            _scheduler_stop.wait(timeout=min(seconds_until_target, 60.0))
            continue

        if _scheduler_stop.is_set():
            break

        logger.info(
            "Déclenchement automatique du batch prévu pour %s.",
            target.isoformat(),
        )
        _run_daily_batch()

        # Recalcul à partir de l'heure courante après la fin du batch.
        target = _compute_next_run(
            now=datetime.now(timezone),
            timezone=timezone,
            hour=hour,
            minute=minute,
        )
        _next_run_time = target

    _next_run_time = None
    logger.info("Scheduler batch quotidien arrêté.")


def start_batch_scheduler() -> Optional[threading.Thread]:
    """Démarre le scheduler quotidien une seule fois dans le processus API."""
    global _scheduler_thread

    with _scheduler_guard:
        if _scheduler_thread is not None and _scheduler_thread.is_alive():
            return _scheduler_thread

        config = get_scheduler_config()

        if not config["enabled"]:
            logger.info("Scheduler batch quotidien désactivé par configuration.")
            _scheduler_thread = None
            return None

        _scheduler_stop.clear()

        thread = threading.Thread(
            target=_scheduler_loop,
            name="neoimpact-daily-batch",
            daemon=True,
        )
        thread.start()
        _scheduler_thread = thread
        return thread


def stop_batch_scheduler() -> None:
    """Arrête proprement le scheduler lors de l'arrêt de FastAPI."""
    global _scheduler_thread

    with _scheduler_guard:
        thread = _scheduler_thread
        _scheduler_thread = None
        _scheduler_stop.set()

    if thread is not None and thread.is_alive():
        thread.join(timeout=2.0)


def get_batch_scheduler_status() -> Dict[str, Any]:
    """Retourne l'état de planification sans déclencher le batch."""
    config = get_scheduler_config()
    thread = _scheduler_thread

    return {
        "enabled": bool(config["enabled"]),
        "running": bool(thread and thread.is_alive()),
        "timezone": config["timezone_name"],
        "hour": int(config["hour"]),
        "minute": int(config["minute"]),
        "next_run_time": (
            _next_run_time.isoformat()
            if _next_run_time is not None
            else None
        ),
    }
