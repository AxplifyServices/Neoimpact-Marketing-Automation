from __future__ import annotations

from contextlib import contextmanager
import os
from typing import Any, Dict, Iterator, List

from app.storage.postgres_db import connection, get_connection


TRACKED_CAMPAIGN_STATES = ("En cours", "En pause", "Planifiée")


def current_change_seq() -> int:
    """Retourne le dernier numéro de changement réellement émis."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT last_value, is_called FROM targeting_change_seq")
            row = cur.fetchone()
    if not row:
        return 0
    return int(row[0] or 0) if bool(row[1]) else 0


def ensure_campaign_state(id_campagne: str) -> Dict[str, Any]:
    campaign_id = str(id_campagne or "").strip()
    if not campaign_id:
        raise ValueError("id_campagne obligatoire")
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO campaign_target_sync_state (id_campagne)
                VALUES (%s)
                ON CONFLICT (id_campagne) DO NOTHING
                """,
                (campaign_id,),
            )
            cur.execute(
                """
                SELECT id_campagne, initialized, watermark, last_sync_at,
                       last_error, updated_at
                FROM campaign_target_sync_state
                WHERE id_campagne = %s
                """,
                (campaign_id,),
            )
            row = cur.fetchone()
    return dict(row or {})


def get_campaign_state(id_campagne: str) -> Dict[str, Any]:
    return ensure_campaign_state(id_campagne)


def initialize_campaign_state(id_campagne: str, watermark: int) -> None:
    campaign_id = str(id_campagne or "").strip()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO campaign_target_sync_state (
                    id_campagne, initialized, watermark, last_sync_at,
                    last_error, updated_at
                )
                VALUES (%s, TRUE, %s, NOW(), NULL, NOW())
                ON CONFLICT (id_campagne)
                DO UPDATE SET
                    initialized = TRUE,
                    watermark = EXCLUDED.watermark,
                    last_sync_at = NOW(),
                    last_error = NULL,
                    updated_at = NOW()
                """,
                (campaign_id, max(0, int(watermark))),
            )


def advance_campaign_watermark(id_campagne: str, watermark: int) -> None:
    campaign_id = str(id_campagne or "").strip()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO campaign_target_sync_state (
                    id_campagne, initialized, watermark, last_sync_at,
                    last_error, updated_at
                )
                VALUES (%s, TRUE, %s, NOW(), NULL, NOW())
                ON CONFLICT (id_campagne)
                DO UPDATE SET
                    initialized = TRUE,
                    watermark = GREATEST(campaign_target_sync_state.watermark, EXCLUDED.watermark),
                    last_sync_at = NOW(),
                    last_error = NULL,
                    updated_at = NOW()
                """,
                (campaign_id, max(0, int(watermark))),
            )


def mark_campaign_error(id_campagne: str, error: str) -> None:
    campaign_id = str(id_campagne or "").strip()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO campaign_target_sync_state (
                    id_campagne, initialized, watermark, last_error, updated_at
                )
                VALUES (%s, FALSE, 0, %s, NOW())
                ON CONFLICT (id_campagne)
                DO UPDATE SET last_error = EXCLUDED.last_error, updated_at = NOW()
                """,
                (campaign_id, str(error or "")[:4000]),
            )


def invalidate_campaigns_for_cible(id_cible: str) -> int:
    """Force un prochain rescan complet si la définition d'une cible change."""
    cible_id = str(id_cible or "").strip()
    if not cible_id:
        return 0
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO campaign_target_sync_state (
                    id_campagne, initialized, watermark, last_error, updated_at
                )
                SELECT c.id_campagne, FALSE, 0, NULL, NOW()
                FROM campagnes AS c
                WHERE c.id_cible = %s
                  AND c.etat_campagne IN ('En cours','En pause','Planifiée')
                ON CONFLICT (id_campagne)
                DO UPDATE SET initialized=FALSE, watermark=0,
                              last_error=NULL, updated_at=NOW()
                """,
                (cible_id,),
            )
            count = cur.rowcount
    return int(count if count is not None and count >= 0 else 0)


def fetch_changed_clients(*, after_seq: int, through_seq: int, limit: int) -> List[Dict[str, Any]]:
    if int(through_seq) <= int(after_seq):
        return []
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT radical_compte, change_seq, changed_at, source
                FROM targeting_client_changes
                WHERE change_seq > %s
                  AND change_seq <= %s
                ORDER BY change_seq ASC
                LIMIT %s
                """,
                (max(0, int(after_seq)), max(0, int(through_seq)), max(1, int(limit))),
            )
            rows = cur.fetchall()
    return [dict(row) for row in rows]


@contextmanager
def campaign_sync_lock(id_campagne: str, *, wait: bool = True) -> Iterator[bool]:
    """Verrou distribué par campagne pour éviter batch + activation simultanés."""
    campaign_id = str(id_campagne or "").strip()
    conn = get_connection(autocommit=True)
    acquired = False
    try:
        with conn.cursor() as cur:
            if wait:
                cur.execute(
                    "SELECT pg_advisory_lock(hashtextextended(%s, 0))",
                    (f"target-sync:{campaign_id}",),
                )
                acquired = True
            else:
                cur.execute(
                    "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))",
                    (f"target-sync:{campaign_id}",),
                )
                row = cur.fetchone()
                acquired = bool(row and row[0])
        yield acquired
    finally:
        if acquired:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                        (f"target-sync:{campaign_id}",),
                    )
            except Exception:
                pass
        conn.close()


def prune_processed_changes() -> int:
    """Purge par petits lots les changements consommés par toutes les campagnes.

    Une suppression massive en une seule transaction générerait inutilement un
    gros pic de WAL/I/O. La purge est donc volontairement bornée et reprendra au
    batch suivant si nécessaire.
    """
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS tracked,
                    COUNT(*) FILTER (
                        WHERE s.id_campagne IS NULL OR s.initialized = FALSE
                    ) AS uninitialized,
                    MIN(s.watermark) FILTER (WHERE s.initialized = TRUE) AS min_watermark
                FROM campagnes AS c
                LEFT JOIN campaign_target_sync_state AS s
                  ON s.id_campagne = c.id_campagne
                WHERE c.etat_campagne IN ('En cours','En pause','Planifiée')
                  AND COALESCE(c.execution_status, 'ready') NOT IN ('failed','cancelled')
                """
            )
            state = dict(cur.fetchone() or {})

    tracked = int(state.get("tracked") or 0)
    uninitialized = int(state.get("uninitialized") or 0)
    if uninitialized > 0:
        return 0

    threshold = current_change_seq() if tracked == 0 else int(state.get("min_watermark") or 0)
    if threshold <= 0:
        return 0

    batch_size = max(1000, min(100000, int(os.getenv("TARGET_SYNC_PRUNE_BATCH_SIZE", "20000") or "20000")))
    max_batches = max(1, min(100, int(os.getenv("TARGET_SYNC_PRUNE_MAX_BATCHES", "20") or "20")))
    deleted_total = 0

    for _ in range(max_batches):
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH doomed AS (
                        SELECT radical_compte
                        FROM targeting_client_changes
                        WHERE change_seq <= %s
                        ORDER BY change_seq
                        LIMIT %s
                    )
                    DELETE FROM targeting_client_changes AS t
                    USING doomed AS d
                    WHERE t.radical_compte = d.radical_compte
                    """,
                    (threshold, batch_size),
                )
                deleted = int(cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0)
        deleted_total += deleted
        if deleted < batch_size:
            break

    return deleted_total


def targeting_stats() -> Dict[str, Any]:
    """Statistiques légères : n_live_tup évite COUNT(*) sur plusieurs millions."""
    seq = current_change_seq()
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(s.n_live_tup, 0)::bigint AS queued_estimate
                FROM pg_stat_user_tables AS s
                WHERE s.relname = 'targeting_client_changes'
                """
            )
            queue_row = cur.fetchone() or {}
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE c.etat_campagne IN ('En cours','En pause','Planifiée')
                          AND COALESCE(c.execution_status,'ready') NOT IN ('failed','cancelled')
                    ) AS tracked_campaigns,
                    COUNT(*) FILTER (
                        WHERE c.etat_campagne IN ('En cours','En pause','Planifiée')
                          AND COALESCE(c.execution_status,'ready') NOT IN ('failed','cancelled')
                          AND (s.id_campagne IS NULL OR s.initialized=FALSE)
                    ) AS uninitialized_campaigns,
                    MIN(s.watermark) FILTER (
                        WHERE c.etat_campagne IN ('En cours','En pause','Planifiée')
                          AND COALESCE(c.execution_status,'ready') NOT IN ('failed','cancelled')
                          AND s.initialized=TRUE
                    ) AS min_watermark
                FROM campagnes AS c
                LEFT JOIN campaign_target_sync_state AS s
                  ON s.id_campagne=c.id_campagne
                """
            )
            campaign_row = cur.fetchone() or {}

    min_watermark = int(campaign_row.get("min_watermark") or seq)
    return {
        "current_change_seq": int(seq),
        "queued_clients_estimate": int(queue_row.get("queued_estimate") or 0),
        "tracked_campaigns": int(campaign_row.get("tracked_campaigns") or 0),
        "uninitialized_campaigns": int(campaign_row.get("uninitialized_campaigns") or 0),
        "max_campaign_lag": max(0, int(seq) - int(min_watermark)),
    }
