from __future__ import annotations

import os
from contextlib import contextmanager
from threading import Condition
from typing import Dict, Iterator


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


class WorkloadGovernor:
    """
    Gouverneur coopératif des traitements lourds dans le processus API.

    Le conteneur lance actuellement un seul processus Uvicorn. Le scheduler batch
    et les endpoints synchrones peuvent néanmoins travailler dans des threads
    concurrents. Ce gouverneur évite qu'ils matérialisent simultanément de gros
    lots en mémoire et donne la priorité aux opérations interactives.

    Important : les tâches batch doivent acquérir/libérer le slot par petit lot,
    afin qu'une requête utilisateur en attente puisse passer au lot suivant.
    """

    def __init__(self) -> None:
        self._max_heavy = _positive_int_env("MAX_CONCURRENT_HEAVY_WORKLOADS", 1)
        self._condition = Condition()
        self._active = 0
        self._waiting_interactive = 0

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
            yield
        finally:
            with self._condition:
                self._active = max(0, self._active - 1)
                self._condition.notify_all()

    def snapshot(self) -> Dict[str, int]:
        with self._condition:
            return {
                "max_concurrent_heavy_workloads": self._max_heavy,
                "active_heavy_workloads": self._active,
                "waiting_interactive_workloads": self._waiting_interactive,
            }


governor = WorkloadGovernor()


def heavy_workload(priority: str = "interactive"):
    return governor.slot(priority=priority)


def workload_snapshot() -> Dict[str, int]:
    return governor.snapshot()
