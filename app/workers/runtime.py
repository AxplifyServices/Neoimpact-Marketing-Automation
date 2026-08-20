from __future__ import annotations

import os
import socket
from typing import Any, Dict, List, Optional

from psycopg.types.json import Jsonb

from app.storage.postgres_db import connection


def instance_id() -> str:
    value = str(os.getenv("WORKER_INSTANCE_ID") or "").strip()
    return value or socket.gethostname()


def _stale_seconds() -> int:
    return max(15, int(os.getenv("WORKER_RUNTIME_STALE_SECONDS", "30") or "30"))


def register_worker(
    worker_type: str,
    *,
    status: str = "starting",
    details: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    worker = str(worker_type or "").strip().lower()
    if not worker:
        raise ValueError("worker_type obligatoire")
    current_instance = instance_id()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO worker_runtime (
                    worker_type, instance_id, pid, status,
                    started_at, heartbeat_at, stopped_at,
                    details_json, last_error, updated_at
                )
                VALUES (%s, %s, %s, %s, NOW(), NOW(), NULL, %s, %s, NOW())
                ON CONFLICT (worker_type, instance_id)
                DO UPDATE SET
                    pid = EXCLUDED.pid,
                    status = EXCLUDED.status,
                    started_at = NOW(),
                    heartbeat_at = NOW(),
                    stopped_at = NULL,
                    details_json = EXCLUDED.details_json,
                    last_error = EXCLUDED.last_error,
                    updated_at = NOW()
                """,
                (
                    worker,
                    current_instance,
                    os.getpid(),
                    status,
                    Jsonb(details or {}),
                    str(error)[:4000] if error else None,
                ),
            )
            # Les anciens IDs de conteneurs ne doivent pas s'accumuler indéfiniment.
            cur.execute(
                """
                DELETE FROM worker_runtime
                WHERE heartbeat_at < NOW() - INTERVAL '7 days'
                """
            )


def heartbeat_worker(
    worker_type: str,
    *,
    status: str = "running",
    details: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    worker = str(worker_type or "").strip().lower()
    current_instance = instance_id()
    missing = False
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE worker_runtime
                SET pid=%s,
                    status=%s,
                    heartbeat_at=NOW(),
                    details_json=%s,
                    last_error=%s,
                    updated_at=NOW()
                WHERE worker_type=%s AND instance_id=%s
                """,
                (
                    os.getpid(),
                    status,
                    Jsonb(details or {}),
                    str(error)[:4000] if error else None,
                    worker,
                    current_instance,
                ),
            )
            missing = cur.rowcount == 0
    if missing:
        register_worker(worker, status=status, details=details, error=error)


def stop_worker(worker_type: str, *, error: Optional[str] = None) -> None:
    worker = str(worker_type or "").strip().lower()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE worker_runtime
                SET status=%s,
                    heartbeat_at=NOW(),
                    stopped_at=NOW(),
                    last_error=%s,
                    updated_at=NOW()
                WHERE worker_type=%s AND instance_id=%s
                """,
                (
                    "error" if error else "stopped",
                    str(error)[:4000] if error else None,
                    worker,
                    instance_id(),
                ),
            )


def worker_group_status(worker_type: str) -> Dict[str, Any]:
    worker = str(worker_type or "").strip().lower()
    stale = _stale_seconds()
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT worker_type, instance_id, pid, status,
                       started_at, heartbeat_at, stopped_at,
                       details_json, last_error,
                       (status='running' AND heartbeat_at >= NOW() - (%s * INTERVAL '1 second')) AS alive
                FROM worker_runtime
                WHERE worker_type=%s
                ORDER BY heartbeat_at DESC
                LIMIT 20
                """,
                (stale, worker),
            )
            rows = [dict(row) for row in cur.fetchall()]

    live = [row for row in rows if bool(row.get("alive"))]
    stale_rows = [row for row in rows if not bool(row.get("alive")) and row.get("status") not in {"stopped"}]
    instances: List[Dict[str, Any]] = []
    for row in rows:
        details = row.get("details_json")
        instances.append(
            {
                "instance_id": row.get("instance_id"),
                "pid": row.get("pid"),
                "status": row.get("status"),
                "alive": bool(row.get("alive")),
                "started_at": row.get("started_at").isoformat() if row.get("started_at") else None,
                "heartbeat_at": row.get("heartbeat_at").isoformat() if row.get("heartbeat_at") else None,
                "details": details if isinstance(details, dict) else {},
                "last_error": row.get("last_error"),
            }
        )
    return {
        "worker_type": worker,
        "healthy": bool(live),
        "live_instances": len(live),
        "stale_instances": len(stale_rows),
        "stale_after_seconds": stale,
        "instances": instances,
    }


def latest_live_worker_details(worker_type: str) -> Dict[str, Any]:
    status = worker_group_status(worker_type)
    for item in status.get("instances") or []:
        if item.get("alive"):
            details = item.get("details")
            return details if isinstance(details, dict) else {}
    return {}


def current_instance_healthy(worker_type: str) -> bool:
    worker = str(worker_type or "").strip().lower()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM worker_runtime
                    WHERE worker_type=%s
                      AND instance_id=%s
                      AND status='running'
                      AND heartbeat_at >= NOW() - (%s * INTERVAL '1 second')
                )
                """,
                (worker, instance_id(), _stale_seconds()),
            )
            row = cur.fetchone()
    return bool(row and row[0])
