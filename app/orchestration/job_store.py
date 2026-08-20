from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.storage.postgres_db import connection


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def enqueue_campaign_prepare(id_campagne: str, *, priority: int = 10) -> Dict[str, Any]:
    campaign_id = str(id_campagne or "").strip()
    if not campaign_id:
        raise ValueError("id_campagne obligatoire")

    job_key = f"campaign_prepare:{campaign_id}"
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO orchestration_jobs (
                    job_key, job_type, priority, status, id_campagne, payload,
                    attempts, max_attempts, available_at, updated_at
                )
                VALUES (%s, 'CAMPAIGN_PREPARE', %s, 'pending', %s, '{}'::jsonb,
                        0, 3, NOW(), NOW())
                ON CONFLICT (job_key)
                DO UPDATE SET
                    priority = LEAST(orchestration_jobs.priority, EXCLUDED.priority),
                    status = CASE
                        WHEN orchestration_jobs.status IN ('failed','cancelled') THEN 'pending'
                        ELSE orchestration_jobs.status
                    END,
                    cancel_requested = FALSE,
                    last_error = CASE
                        WHEN orchestration_jobs.status IN ('failed','cancelled') THEN NULL
                        ELSE orchestration_jobs.last_error
                    END,
                    available_at = CASE
                        WHEN orchestration_jobs.status IN ('failed','cancelled') THEN NOW()
                        ELSE orchestration_jobs.available_at
                    END,
                    updated_at = NOW()
                RETURNING *
                """,
                (max(0, int(priority)), campaign_id),
            )
            row = cur.fetchone()
    return dict(row or {})


def claim_next_job(*, stale_after_seconds: int = 3600) -> Optional[Dict[str, Any]]:
    stale_seconds = max(60, int(stale_after_seconds))
    worker = _worker_id()

    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH candidate AS (
                    SELECT id
                    FROM orchestration_jobs
                    WHERE cancel_requested = FALSE
                      AND attempts < max_attempts
                      AND (
                            (status IN ('pending','retry') AND available_at <= NOW())
                            OR
                            (status = 'processing'
                             AND COALESCE(heartbeat_at, locked_at) < NOW() - (%s * INTERVAL '1 second'))
                          )
                    ORDER BY priority ASC, available_at ASC, id ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE orchestration_jobs AS j
                SET status = 'processing',
                    attempts = j.attempts + 1,
                    locked_at = NOW(),
                    locked_by = %s,
                    heartbeat_at = NOW(),
                    updated_at = NOW(),
                    last_error = NULL
                FROM candidate
                WHERE j.id = candidate.id
                RETURNING j.*
                """,
                (stale_seconds, worker),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def heartbeat_job(job_id: int, *, current: Optional[int] = None, total: Optional[int] = None, message: Optional[str] = None) -> None:
    sets = ["heartbeat_at = NOW()", "updated_at = NOW()"]
    params: list[Any] = []
    if current is not None:
        sets.append("progress_current = %s")
        params.append(max(0, int(current)))
    if total is not None:
        sets.append("progress_total = %s")
        params.append(max(0, int(total)))
    if message is not None:
        sets.append("progress_message = %s")
        params.append(str(message)[:500])
    params.append(int(job_id))

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE orchestration_jobs SET {', '.join(sets)} WHERE id = %s AND status = 'processing'",
                params,
            )


def is_cancel_requested(job_id: int) -> bool:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT cancel_requested OR status = 'cancelled' FROM orchestration_jobs WHERE id = %s",
                (int(job_id),),
            )
            row = cur.fetchone()
    return bool(row and row[0])


def complete_job(job_id: int, *, message: str = "Terminé") -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE orchestration_jobs
                SET status='succeeded',
                    progress_current = GREATEST(progress_current, progress_total),
                    progress_message=%s,
                    locked_at=NULL,
                    locked_by=NULL,
                    heartbeat_at=NOW(),
                    updated_at=NOW(),
                    finished_at=NOW(),
                    last_error=NULL
                WHERE id=%s
                """,
                (str(message)[:500], int(job_id)),
            )


def fail_job(job_id: int, error: str) -> str:
    err = str(error or "Erreur inconnue")[:4000]
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT attempts, max_attempts, cancel_requested FROM orchestration_jobs WHERE id=%s FOR UPDATE",
                (int(job_id),),
            )
            row = cur.fetchone()
            if not row:
                return "missing"
            if bool(row.get("cancel_requested")):
                status = "cancelled"
                delay_seconds = 0
            elif int(row.get("attempts") or 0) >= int(row.get("max_attempts") or 3):
                status = "failed"
                delay_seconds = 0
            else:
                status = "retry"
                delay_seconds = min(300, 2 ** max(1, int(row.get("attempts") or 1)))

            cur.execute(
                """
                UPDATE orchestration_jobs
                SET status=%s,
                    last_error=%s,
                    progress_message=%s,
                    available_at = NOW() + (%s * INTERVAL '1 second'),
                    locked_at=NULL,
                    locked_by=NULL,
                    updated_at=NOW(),
                    finished_at=CASE WHEN %s IN ('failed','cancelled') THEN NOW() ELSE NULL END
                WHERE id=%s
                """,
                (status, err, "Nouvelle tentative" if status == "retry" else err[:500], delay_seconds, status, int(job_id)),
            )
    return status


def request_cancel_for_campaign(id_campagne: str) -> int:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE orchestration_jobs
                SET cancel_requested=TRUE,
                    status=CASE WHEN status IN ('pending','retry') THEN 'cancelled' ELSE status END,
                    finished_at=CASE WHEN status IN ('pending','retry') THEN NOW() ELSE finished_at END,
                    updated_at=NOW()
                WHERE id_campagne=%s
                  AND status IN ('pending','retry','processing')
                """,
                (str(id_campagne),),
            )
            count = cur.rowcount
    return int(count if count is not None and count >= 0 else 0)


def get_campaign_job_status(id_campagne: str) -> Optional[Dict[str, Any]]:
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, job_type, status, attempts, max_attempts,
                       progress_current, progress_total, progress_message,
                       last_error, created_at, updated_at, finished_at
                FROM orchestration_jobs
                WHERE id_campagne=%s
                ORDER BY id DESC
                LIMIT 1
                """,
                (str(id_campagne),),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def orchestration_stats() -> Dict[str, int]:
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status='pending') AS pending,
                    COUNT(*) FILTER (WHERE status='processing') AS processing,
                    COUNT(*) FILTER (WHERE status='retry') AS retry,
                    COUNT(*) FILTER (WHERE status='failed') AS failed
                FROM orchestration_jobs
                """
            )
            row = cur.fetchone() or {}
    return {key: int(row.get(key) or 0) for key in ("pending", "processing", "retry", "failed")}
