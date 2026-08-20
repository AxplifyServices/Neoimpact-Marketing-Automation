from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

from app.storage.runtime_db import connect_runtime


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def make_event_key(channel: str, event_type: str, payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    raw = f"{_norm(channel).upper()}\x1f{_norm(event_type)}\x1f{canonical}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def enqueue_event(
    *,
    channel: str,
    event_type: str,
    payload: Dict[str, Any],
    id_campagne: str = "",
    radical_compte: str = "",
    block_id: str = "",
    event_key: Optional[str] = None,
) -> Dict[str, Any]:
    key = _norm(event_key) or make_event_key(channel, event_type, payload)
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO inbound_events (
                event_key,channel,event_type,id_campagne,radical_compte,block_id,
                payload_json,status,attempts,max_attempts,available_at,created_at,updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?::jsonb, 'pending', 0, 5, NOW(), NOW(), NOW())
            ON CONFLICT (event_key) DO NOTHING
            RETURNING id
            """,
            (
                key,
                _norm(channel).upper(),
                _norm(event_type),
                _norm(id_campagne) or None,
                _norm(radical_compte) or None,
                _norm(block_id) or None,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return {"ok": True, "accepted": True, "duplicate": row is None, "event_key": key}
    finally:
        conn.close()


def claim_next(*, stale_seconds: int = 300) -> Optional[Dict[str, Any]]:
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            WITH candidate AS (
                SELECT id
                FROM inbound_events
                WHERE attempts < max_attempts
                  AND available_at <= NOW()
                  AND (
                      status IN ('pending','retry')
                      OR (status='processing' AND locked_at < NOW() - (? || ' seconds')::interval)
                  )
                ORDER BY available_at,id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE inbound_events e
            SET status='processing', attempts=e.attempts+1, locked_at=NOW(), updated_at=NOW()
            FROM candidate
            WHERE e.id=candidate.id
            RETURNING e.*
            """,
            (max(30, int(stale_seconds)),),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None
    finally:
        conn.close()


def complete(event_id: int) -> None:
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE inbound_events SET status='completed',processed_at=NOW(),last_error=NULL,updated_at=NOW() WHERE id=? AND status='processing'",
            (int(event_id),),
        )
        conn.commit()
    finally:
        conn.close()


def fail(event_id: int, error: str) -> str:
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute("SELECT attempts,max_attempts FROM inbound_events WHERE id=? FOR UPDATE", (int(event_id),))
        row = cur.fetchone()
        if not row:
            conn.rollback()
            return "missing"
        attempts = int(row.get("attempts") or 0)
        max_attempts = int(row.get("max_attempts") or 5)
        if attempts >= max_attempts:
            status = "failed"
            cur.execute(
                "UPDATE inbound_events SET status='failed',last_error=?,processed_at=NOW(),updated_at=NOW() WHERE id=? AND status='processing'",
                (_norm(error)[:4000], int(event_id)),
            )
        else:
            status = "retry"
            delay = min(900, 2 ** max(0, attempts - 1) * 5)
            cur.execute(
                "UPDATE inbound_events SET status='retry',last_error=?,available_at=NOW()+(? || ' seconds')::interval,updated_at=NOW() WHERE id=? AND status='processing'",
                (_norm(error)[:4000], delay, int(event_id)),
            )
        conn.commit()
        return status
    finally:
        conn.close()


def stats() -> Dict[str, int]:
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute("SELECT status,COUNT(*) AS n FROM inbound_events GROUP BY status")
        return {str(r["status"]): int(r["n"] or 0) for r in cur.fetchall()}
    finally:
        conn.close()
