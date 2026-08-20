from __future__ import annotations

import os
import time
from contextlib import contextmanager
from threading import Condition
from typing import Dict, Iterator, Optional


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


class WorkloadGovernor:
    """Gouverneur coopératif des traitements lourds.

    Deux protections complémentaires:
    - priorité locale aux opérations utilisateur face aux petits lots batch;
    - advisory lock PostgreSQL pour empêcher deux processus/conteneurs de lancer
      simultanément les écritures les plus lourdes sur la même instance.

    Les I/O réseau (webhooks / APIs sortantes) restent volontairement hors de ce
    verrou global et peuvent être parallélisées avec une concurrence bornée.
    """

    def __init__(self) -> None:
        self._max_heavy = _positive_int_env("MAX_CONCURRENT_HEAVY_WORKLOADS", 1)
        self._condition = Condition()
        self._active = 0
        self._waiting_interactive = 0
        self._global_lock_enabled = str(
            os.getenv("GLOBAL_HEAVY_WORKLOAD_LOCK_ENABLED", "true")
        ).strip().lower() not in {"0", "false", "no", "off"}
        self._global_lock_key = int(os.getenv("GLOBAL_HEAVY_WORKLOAD_LOCK_KEY", "620020") or "620020")

    @contextmanager
    def _distributed_lock(self) -> Iterator[None]:
        if not self._global_lock_enabled:
            yield
            return

        # Import tardif: l'application peut démarrer avant que PostgreSQL soit
        # totalement disponible; seule une opération lourde exige ce verrou.
        from app.storage.postgres_db import get_connection

        conn = get_connection(autocommit=True)
        acquired = False
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_lock(%s)", (self._global_lock_key,))
                acquired = True
            yield
        finally:
            if acquired:
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT pg_advisory_unlock(%s)", (self._global_lock_key,))
                except Exception:
                    pass
            conn.close()

    @contextmanager
    def slot(self, priority: str = "interactive") -> Iterator[None]:
        priority = str(priority or "interactive").strip().lower()
        interactive = priority != "batch"

        with self._condition:
            if interactive:
                self._waiting_interactive += 1
            try:
                while self._active >= self._max_heavy or (
                    not interactive and self._waiting_interactive > 0
                ):
                    self._condition.wait()
                self._active += 1
            finally:
                if interactive:
                    self._waiting_interactive -= 1

        try:
            with self._distributed_lock():
                yield
        finally:
            with self._condition:
                self._active = max(0, self._active - 1)
                self._condition.notify_all()

    def snapshot(self) -> Dict[str, int | bool]:
        with self._condition:
            return {
                "max_concurrent_heavy_workloads": self._max_heavy,
                "active_heavy_workloads": self._active,
                "waiting_interactive_workloads": self._waiting_interactive,
                "global_heavy_lock_enabled": self._global_lock_enabled,
            }


governor = WorkloadGovernor()


def heavy_workload(priority: str = "interactive"):
    return governor.slot(priority=priority)


def workload_snapshot() -> Dict[str, int | bool]:
    return governor.snapshot()
