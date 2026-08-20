from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional, Sequence

from app.storage.runtime_db import connect_runtime

ACTIVE_STATUSES = ("pending", "retry", "processing")
TERMINAL_STATUSES = ("completed", "failed", "cancelled", "obsolete")


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enqueue_candidates(
    *,
    id_campagne: Optional[str] = None,
    channels: Sequence[str] = ("MAIL", "TERRAIN"),
    limit_per_channel: int = 1000,
) -> Dict[str, int]:
    """Publie un lot borné d'actions externes sans matérialiser la population.

    Le marqueur outbound_enqueued_key rend la découverte incrémentale : une ligne
    déjà publiée quitte l'ensemble candidat jusqu'à ce que son bloc/occurrence
    change.
    """
    result: Dict[str, int] = {}
    campaign = _norm(id_campagne)
    limit = max(1, int(limit_per_channel))

    for raw_channel in channels:
        channel = _norm(raw_channel).upper()
        if channel not in {"MAIL", "TERRAIN"}:
            continue

        if channel == "MAIL":
            action_predicate = """
                COALESCE(cc.\"Canal\", '') = 'Mail'
                AND COALESCE(cc.\"Action\", '') IN ('Message', 'Mail')
            """
            provider = "SMTP"
        else:
            action_predicate = """
                COALESCE(c.type_campagne, '') = 'avec_action_terrain'
                AND COALESCE(cc.\"Action\", '') IN ('Directeur d''agence', 'Conseiller client')
            """
            provider = "VISITS_API"

        campaign_clause = ""
        params: list[Any] = [channel, provider]
        if campaign:
            campaign_clause = "AND cc.\"ID_CAMPAGNE\" = ?"
            params.append(campaign)
        params.append(limit)

        sql = f"""
            WITH candidates AS (
                SELECT
                    cc.id AS client_campaign_id,
                    cc.\"ID_CAMPAGNE\" AS id_campagne,
                    cc.\"Radical_compte\" AS radical_compte,
                    cc.\"ID_Action\" AS block_id,
                    COALESCE(cc.action_execution_seq, 0) AS occurrence,
                    COALESCE(cc.\"ID_Action\", '') || ':' ||
                        COALESCE(cc.action_execution_seq, 0)::text || ':' || ? AS enqueue_key
                FROM clients_campagnes cc
                INNER JOIN campagnes c ON c.id_campagne = cc.\"ID_CAMPAGNE\"
                WHERE COALESCE(cc.\"Etat_campagne\", '') = 'En cours'
                  AND COALESCE(cc.conversion, 0) <> 1
                  AND COALESCE(c.etat_campagne, '') = 'En cours'
                  AND COALESCE(c.execution_status, 'ready') = 'ready'
                  AND COALESCE(cc.\"ID_Action\", '') <> ''
                  AND {action_predicate}
                  {campaign_clause}
                  AND COALESCE(cc.outbound_enqueued_key, '') <>
                      COALESCE(cc.\"ID_Action\", '') || ':' ||
                      COALESCE(cc.action_execution_seq, 0)::text || ':' || ?
                ORDER BY cc.id
                FOR UPDATE OF cc SKIP LOCKED
                LIMIT ?
            ), inserted AS (
                INSERT INTO outbound_dispatches (
                    client_campaign_id, id_campagne, radical_compte, block_id,
                    occurrence, channel, provider, status, priority,
                    attempts, max_attempts, available_at, created_at, updated_at
                )
                SELECT
                    client_campaign_id, id_campagne, radical_compte, block_id,
                    occurrence, ?, ?, 'pending', 100,
                    0, 5, NOW(), NOW(), NOW()
                FROM candidates
                ON CONFLICT (id_campagne, radical_compte, block_id, occurrence, channel)
                DO NOTHING
                RETURNING id
            )
            UPDATE clients_campagnes cc
            SET outbound_enqueued_key = candidates.enqueue_key
            FROM candidates
            WHERE cc.id = candidates.client_campaign_id
            RETURNING cc.id
        """
        # channel appears twice before provider in the CTE/INSERT.
        full_params: list[Any] = [channel]
        if campaign:
            full_params.append(campaign)
        full_params.extend([channel, limit, channel, provider])

        conn = connect_runtime()
        try:
            cur = conn.cursor()
            cur.execute(sql, full_params)
            rows = cur.fetchall()
            conn.commit()
            result[channel] = len(rows)
        finally:
            conn.close()

    return result


def enqueue_single(id_campagne: str, radical_compte: str, *, channel: str) -> Dict[str, Any]:
    campaign = _norm(id_campagne)
    radical = _norm(radical_compte)
    channel = _norm(channel).upper()
    if not campaign or not radical or channel not in {"MAIL", "TERRAIN"}:
        return {"ok": False, "error": "invalid_dispatch_keys"}

    # Le producteur SQL reste la source de vérité; la clause campagne/client
    # ci-dessous permet seulement de publier rapidement une transition unitaire.
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        if channel == "MAIL":
            predicate = "COALESCE(cc.\"Canal\", '')='Mail' AND COALESCE(cc.\"Action\", '') IN ('Message','Mail')"
            provider = "SMTP"
        else:
            predicate = "COALESCE(c.type_campagne,'')='avec_action_terrain' AND COALESCE(cc.\"Action\", '') IN ('Directeur d''agence','Conseiller client')"
            provider = "VISITS_API"
        cur.execute(
            f"""
            SELECT cc.id, cc.\"ID_Action\" AS block_id,
                   COALESCE(cc.action_execution_seq,0) AS occurrence
            FROM clients_campagnes cc
            JOIN campagnes c ON c.id_campagne=cc.\"ID_CAMPAGNE\"
            WHERE cc.\"ID_CAMPAGNE\"=? AND cc.\"Radical_compte\"=?
              AND COALESCE(cc.\"Etat_campagne\",'')='En cours'
              AND COALESCE(c.etat_campagne,'')='En cours'
              AND COALESCE(cc.conversion,0)<>1
              AND {predicate}
            LIMIT 1
            """,
            (campaign, radical),
        )
        row = cur.fetchone()
        if not row:
            return {"ok": True, "queued": False, "reason": "not_eligible"}
        block_id = _norm(row.get("block_id"))
        occurrence = int(row.get("occurrence") or 0)
        enqueue_key = f"{block_id}:{occurrence}:{channel}"
        cur.execute(
            """
            INSERT INTO outbound_dispatches (
                client_campaign_id,id_campagne,radical_compte,block_id,occurrence,
                channel,provider,status,priority,attempts,max_attempts,available_at,created_at,updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 50, 0, 5, NOW(), NOW(), NOW())
            ON CONFLICT (id_campagne,radical_compte,block_id,occurrence,channel) DO NOTHING
            """,
            (int(row["id"]), campaign, radical, block_id, occurrence, channel, provider),
        )
        inserted = int(cur.rowcount or 0)
        cur.execute(
            "UPDATE clients_campagnes SET outbound_enqueued_key=? WHERE id=?",
            (enqueue_key, int(row["id"])),
        )
        conn.commit()
        return {"ok": True, "queued": bool(inserted), "channel": channel}
    finally:
        conn.close()


def claim_next(channel: str, *, stale_seconds: int = 300) -> Optional[Dict[str, Any]]:
    channel = _norm(channel).upper()
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            WITH candidate AS (
                SELECT d.id
                FROM outbound_dispatches d
                JOIN campagnes c ON c.id_campagne=d.id_campagne
                WHERE d.channel=?
                  AND COALESCE(c.etat_campagne,'')='En cours'
                  AND COALESCE(c.execution_status,'ready')='ready'
                  AND d.attempts < d.max_attempts
                  AND d.available_at <= NOW()
                  AND (
                      d.status IN ('pending','retry')
                      OR (d.status='processing' AND d.heartbeat_at < NOW() - (? || ' seconds')::interval)
                  )
                ORDER BY d.priority, d.available_at, d.id
                FOR UPDATE OF d SKIP LOCKED
                LIMIT 1
            )
            UPDATE outbound_dispatches d
            SET status='processing',
                attempts=d.attempts+1,
                locked_at=NOW(), heartbeat_at=NOW(), updated_at=NOW()
            FROM candidate
            WHERE d.id=candidate.id
            RETURNING d.*
            """,
            (channel, max(30, int(stale_seconds))),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None
    finally:
        conn.close()


def dispatch_is_current(item: Dict[str, Any]) -> bool:
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1
            FROM clients_campagnes cc
            JOIN campagnes c ON c.id_campagne=cc.\"ID_CAMPAGNE\"
            WHERE cc.id=?
              AND cc.\"ID_CAMPAGNE\"=?
              AND cc.\"Radical_compte\"=?
              AND cc.\"ID_Action\"=?
              AND COALESCE(cc.action_execution_seq,0)=?
              AND COALESCE(cc.\"Etat_campagne\",'')='En cours'
              AND COALESCE(c.etat_campagne,'')='En cours'
              AND COALESCE(cc.conversion,0)<>1
            LIMIT 1
            """,
            (
                int(item.get("client_campaign_id") or 0),
                _norm(item.get("id_campagne")),
                _norm(item.get("radical_compte")),
                _norm(item.get("block_id")),
                int(item.get("occurrence") or 0),
            ),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def mark_success(dispatch_id: int, *, waiting_callback: bool = False, response: Any = None) -> bool:
    status = "waiting_callback" if waiting_callback else "completed"
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE outbound_dispatches
            SET status=?, sent_at=COALESCE(sent_at,NOW()),
                completed_at=CASE WHEN ?='completed' THEN NOW() ELSE completed_at END,
                response_json=?::jsonb, last_error=NULL, heartbeat_at=NOW(), updated_at=NOW()
            WHERE id=? AND status='processing'
            """,
            (status, status, response if isinstance(response, str) else None, int(dispatch_id)),
        )
        changed = int(cur.rowcount or 0) > 0
        conn.commit()
        return changed
    finally:
        conn.close()


def mark_obsolete(dispatch_id: int, reason: str = "workflow_moved") -> None:
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE outbound_dispatches SET status='obsolete', last_error=?, completed_at=NOW(), updated_at=NOW() WHERE id=? AND status='processing'",
            (_norm(reason), int(dispatch_id)),
        )
        conn.commit()
    finally:
        conn.close()


def mark_failure(dispatch_id: int, error: str) -> str:
    """Planifie un retry exponentiel ou clôture définitivement le dispatch."""
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute("SELECT attempts,max_attempts FROM outbound_dispatches WHERE id=? FOR UPDATE", (int(dispatch_id),))
        row = cur.fetchone()
        if not row:
            conn.rollback()
            return "missing"
        attempts = int(row.get("attempts") or 0)
        max_attempts = int(row.get("max_attempts") or 5)
        if attempts >= max_attempts:
            status = "failed"
            cur.execute(
                "UPDATE outbound_dispatches SET status='failed', last_error=?, completed_at=NULL, updated_at=NOW() WHERE id=? AND status='processing'",
                (_norm(error)[:4000], int(dispatch_id)),
            )
        else:
            status = "retry"
            delay = min(900, 2 ** max(0, attempts - 1) * 5)
            cur.execute(
                """
                UPDATE outbound_dispatches
                SET status='retry', last_error=?,
                    available_at=NOW() + (? || ' seconds')::interval,
                    updated_at=NOW()
                WHERE id=? AND status='processing'
                """,
                (_norm(error)[:4000], delay, int(dispatch_id)),
            )
        conn.commit()
        return status
    finally:
        conn.close()


def cancel_for_campaign(id_campagne: str) -> int:
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE outbound_dispatches
            SET status='cancelled', completed_at=NOW(), updated_at=NOW(), last_error='campaign_cancelled'
            WHERE id_campagne=? AND status IN ('pending','retry')
            """,
            (_norm(id_campagne),),
        )
        count = int(cur.rowcount or 0)
        conn.commit()
        return count
    finally:
        conn.close()


def stats(id_campagne: Optional[str] = None, channel: Optional[str] = None) -> Dict[str, int]:
    where: list[str] = []
    params: list[Any] = []
    if _norm(id_campagne):
        where.append("id_campagne=?")
        params.append(_norm(id_campagne))
    if _norm(channel):
        where.append("channel=?")
        params.append(_norm(channel).upper())
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT status,COUNT(*) AS n FROM outbound_dispatches{clause} GROUP BY status", params)
        return {str(r["status"]): int(r["n"] or 0) for r in cur.fetchall()}
    finally:
        conn.close()


def active_depth(channel: Optional[str] = None) -> int:
    where = "WHERE status IN ('pending','retry','processing')"
    params: list[Any] = []
    if _norm(channel):
        where += " AND channel=?"
        params.append(_norm(channel).upper())
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) AS n FROM outbound_dispatches {where}", params)
        row = cur.fetchone()
        return int((row or {}).get("n") or 0)
    finally:
        conn.close()


def mark_network_sent(dispatch_id: int, response: Any = None) -> bool:
    """Persiste le succès réseau avant toute progression métier.

    Pour Mail cela sépare l'effet externe (déjà irréversible) de la finalisation
    du workflow. Un crash après cette étape ne provoque donc pas un renvoi SMTP.
    """
    import json
    response_json = json.dumps(response, ensure_ascii=False) if response is not None else None
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE outbound_dispatches
            SET status='sent', sent_at=COALESCE(sent_at,NOW()), response_json=?::jsonb,
                last_error=NULL, heartbeat_at=NOW(), updated_at=NOW()
            WHERE id=? AND status='processing'
            """,
            (response_json, int(dispatch_id)),
        )
        changed = int(cur.rowcount or 0) > 0
        conn.commit()
        return changed
    finally:
        conn.close()


def claim_sent_for_finalize(channel: str, *, stale_seconds: int = 300) -> Optional[Dict[str, Any]]:
    channel = _norm(channel).upper()
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            WITH candidate AS (
                SELECT id
                FROM outbound_dispatches
                WHERE channel=?
                  AND completed_at IS NULL
                  AND (
                      status='sent'
                      OR (status='finalizing' AND heartbeat_at < NOW()-(? || ' seconds')::interval)
                  )
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE outbound_dispatches d
            SET status='finalizing', heartbeat_at=NOW(), updated_at=NOW()
            FROM candidate
            WHERE d.id=candidate.id
            RETURNING d.*
            """,
            (channel, max(30, int(stale_seconds))),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None
    finally:
        conn.close()


def complete_finalizing(dispatch_id: int) -> bool:
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE outbound_dispatches
            SET status='completed', completed_at=NOW(), last_error=NULL, updated_at=NOW()
            WHERE id=? AND status='finalizing'
            """,
            (int(dispatch_id),),
        )
        changed = int(cur.rowcount or 0) > 0
        conn.commit()
        return changed
    finally:
        conn.close()


def claim_mail_finalize(*, stale_seconds: int = 300) -> Optional[Dict[str, Any]]:
    """Réclame un Mail déjà envoyé ou définitivement échoué sans le renvoyer."""
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            WITH candidate AS (
                SELECT id,status AS delivery_status
                FROM outbound_dispatches
                WHERE channel='MAIL' AND completed_at IS NULL
                  AND (
                      status IN ('sent','failed')
                      OR (status IN ('finalizing','finalizing_failed')
                          AND heartbeat_at < NOW()-(? || ' seconds')::interval)
                  )
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE outbound_dispatches d
            SET status=CASE
                    WHEN candidate.delivery_status IN ('failed','finalizing_failed') THEN 'finalizing_failed'
                    ELSE 'finalizing'
                END,
                heartbeat_at=NOW(), updated_at=NOW()
            FROM candidate
            WHERE d.id=candidate.id
            RETURNING d.*, candidate.delivery_status
            """,
            (max(30, int(stale_seconds)),),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None
    finally:
        conn.close()


def complete_mail_finalize(dispatch_id: int, *, delivered: bool) -> bool:
    final_status = "completed" if delivered else "failed"
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE outbound_dispatches
            SET status=?, completed_at=NOW(), updated_at=NOW()
            WHERE id=? AND status IN ('finalizing','finalizing_failed','sent','failed')
            """,
            (final_status, int(dispatch_id)),
        )
        changed = int(cur.rowcount or 0) > 0
        conn.commit()
        return changed
    finally:
        conn.close()


def resume_paused_for_campaign(id_campagne: str) -> int:
    """Réactive les dispatchs terrain annulés côté fournisseur lors d'une pause."""
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE outbound_dispatches
            SET status='pending', available_at=NOW(), attempts=0, last_error=NULL,
                completed_at=NULL, updated_at=NOW()
            WHERE id_campagne=? AND status='paused'
            """,
            (_norm(id_campagne),),
        )
        count = int(cur.rowcount or 0)
        conn.commit()
        return count
    finally:
        conn.close()
