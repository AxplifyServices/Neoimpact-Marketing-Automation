from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from psycopg.types.json import Jsonb

from app.storage.postgres_db import connection


def _normalize(row: Any) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    data = dict(row)
    for key in ("requested_at", "started_at", "heartbeat_at", "finished_at", "available_at", "updated_at"):
        value = data.get(key)
        if value is not None and hasattr(value, "isoformat"):
            data[key] = value.isoformat()
    return data


def enqueue_request(*, trigger: str = "manual_api", parameters: Optional[Dict[str, Any]] = None) -> Tuple[bool, Dict[str, Any]]:
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO batch_run_requests (trigger, parameters_json)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                RETURNING *
                """,
                (str(trigger or "manual_api"), Jsonb(parameters or {})),
            )
            row = cur.fetchone()
            if row is not None:
                return True, _normalize(row) or {}
            cur.execute(
                """
                SELECT *
                FROM batch_run_requests
                WHERE status IN ('pending','processing')
                ORDER BY requested_at DESC, id DESC
                LIMIT 1
                """
            )
            active = cur.fetchone()
    return False, _normalize(active) or {}


def claim_next_request(*, worker_id: str, stale_seconds: int = 120) -> Optional[Dict[str, Any]]:
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            # Un traitement abandonné redevient récupérable après disparition du heartbeat.
            cur.execute(
                """
                UPDATE batch_run_requests
                SET status='pending', locked_by=NULL, started_at=NULL,
                    heartbeat_at=NULL, available_at=NOW(), updated_at=NOW()
                WHERE status='processing'
                  AND COALESCE(heartbeat_at, started_at, requested_at)
                      < NOW() - (%s * INTERVAL '1 second')
                """,
                (max(30, int(stale_seconds)),),
            )
            cur.execute(
                """
                WITH picked AS (
                    SELECT id
                    FROM batch_run_requests
                    WHERE status='pending'
                      AND available_at <= NOW()
                    ORDER BY requested_at ASC, id ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE batch_run_requests AS r
                SET status='processing',
                    attempts=r.attempts+1,
                    locked_by=%s,
                    started_at=COALESCE(r.started_at, NOW()),
                    heartbeat_at=NOW(),
                    error=NULL,
                    updated_at=NOW()
                FROM picked
                WHERE r.id=picked.id
                RETURNING r.*
                """,
                (str(worker_id),),
            )
            row = cur.fetchone()
    return _normalize(row)


def heartbeat_request(request_id: int, *, worker_id: str) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE batch_run_requests
                SET heartbeat_at=NOW(), updated_at=NOW()
                WHERE id=%s AND status='processing' AND locked_by=%s
                """,
                (int(request_id), str(worker_id)),
            )


def complete_request(request_id: int, result: Dict[str, Any]) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE batch_run_requests
                SET status='completed', result_json=%s, error=NULL,
                    heartbeat_at=NOW(), finished_at=NOW(), updated_at=NOW()
                WHERE id=%s
                """,
                (Jsonb(result or {}), int(request_id)),
            )


def fail_request(request_id: int, error: str) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE batch_run_requests
                SET status='failed', error=%s, heartbeat_at=NOW(),
                    finished_at=NOW(), updated_at=NOW()
                WHERE id=%s
                """,
                (str(error or "")[:4000], int(request_id)),
            )


def requeue_request(request_id: int, *, delay_seconds: int = 30, error: Optional[str] = None) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE batch_run_requests
                SET status='pending', locked_by=NULL, heartbeat_at=NULL,
                    available_at=NOW() + (%s * INTERVAL '1 second'),
                    error=%s, updated_at=NOW()
                WHERE id=%s
                """,
                (max(1, int(delay_seconds)), str(error or "")[:4000] or None, int(request_id)),
            )


def latest_request() -> Optional[Dict[str, Any]]:
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM batch_run_requests
                ORDER BY requested_at DESC, id DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
    return _normalize(row)
