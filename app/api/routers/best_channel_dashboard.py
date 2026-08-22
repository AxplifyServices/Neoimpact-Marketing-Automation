from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from app.best_channel.history import CANONICAL_CHANNELS
from app.best_channel.model import load_metadata, model_exists
from app.storage.postgres_db import connection

router = APIRouter()


def _as_int(value: Any) -> int:
    return int(value or 0)


def _as_float(value: Any) -> float:
    return float(value or 0.0)


def _latest_month() -> int | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(annee_mois) FROM dm_best_channel_scores")
            row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else None


@router.get("/data-tools/best-channel/filters")
def best_channel_filters() -> Dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT annee_mois
                FROM dm_best_channel_scores
                ORDER BY annee_mois DESC
                """
            )
            months = [int(row[0]) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT DISTINCT region
                FROM dm_best_channel_scores
                WHERE region IS NOT NULL AND BTRIM(region) <> ''
                ORDER BY region
                """
            )
            regions = [str(row[0]) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT DISTINCT statut_client_snapshot
                FROM dm_best_channel_scores
                WHERE statut_client_snapshot IS NOT NULL
                  AND BTRIM(statut_client_snapshot) <> ''
                ORDER BY statut_client_snapshot
                """
            )
            statuses = [str(row[0]) for row in cur.fetchall()]

    return {
        "months": months,
        "default_annee_mois": months[0] if months else None,
        "regions": regions,
        "statuses": statuses,
        "channels": list(CANONICAL_CHANNELS),
    }


@router.get("/data-tools/best-channel/dashboard")
def best_channel_dashboard(
    annee_mois: Optional[int] = Query(default=None, ge=190001, le=299912),
    region: Optional[str] = Query(default=None, max_length=150),
    statut_client: Optional[str] = Query(default=None, max_length=80),
) -> Dict[str, Any]:
    month = int(annee_mois or (_latest_month() or 0))
    region = (region or "").strip() or None
    statut_client = (statut_client or "").strip() or None

    if month <= 0:
        return {
            "filters": {"annee_mois": None, "region": region, "statut_client": statut_client},
            "summary": {},
            "top1_distribution": [],
            "top3_distribution": [],
            "regions": [],
            "training": {},
            "model": {"exists": model_exists()},
        }

    score_where = ["s.annee_mois = %s"]
    score_params: List[Any] = [month]
    if region:
        score_where.append("s.region = %s")
        score_params.append(region)
    if statut_client:
        score_where.append("s.statut_client_snapshot = %s")
        score_params.append(statut_client)
    score_where_sql = " AND ".join(score_where)

    interaction_where = [
        "i.finalized_at IS NOT NULL",
        "i.observed_at >= CURRENT_DATE - INTERVAL '12 months'",
    ]
    interaction_params: List[Any] = []
    if region:
        interaction_where.append("COALESCE(i.region, 'Inconnue') = %s")
        interaction_params.append(region)
    interaction_where_sql = " AND ".join(interaction_where)

    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS scored_clients,
                    AVG(s.score_top1) AS avg_top1_score,
                    MAX(s.score_top1) AS max_top1_score,
                    MAX(s.date_scoring) AS last_scoring,
                    COUNT(*) FILTER (WHERE s.canal_top1 = 'non_score') AS non_scored
                FROM dm_best_channel_scores AS s
                WHERE {score_where_sql}
                """,
                score_params,
            )
            score_summary = dict(cur.fetchone() or {})

            cur.execute(
                f"""
                SELECT
                    s.canal_top1 AS canal,
                    COUNT(*) AS clients,
                    AVG(s.score_top1) AS avg_score
                FROM dm_best_channel_scores AS s
                WHERE {score_where_sql}
                GROUP BY s.canal_top1
                ORDER BY clients DESC, canal
                """,
                score_params,
            )
            top1_distribution = [dict(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                WITH ranked AS (
                    SELECT s.canal_top1 AS canal, 1 AS rang, s.score_top1 AS score
                    FROM dm_best_channel_scores s
                    WHERE {score_where_sql}
                    UNION ALL
                    SELECT s.canal_top2 AS canal, 2 AS rang, s.score_top2 AS score
                    FROM dm_best_channel_scores s
                    WHERE {score_where_sql}
                    UNION ALL
                    SELECT s.canal_top3 AS canal, 3 AS rang, s.score_top3 AS score
                    FROM dm_best_channel_scores s
                    WHERE {score_where_sql}
                )
                SELECT
                    canal,
                    COUNT(*) FILTER (WHERE rang = 1) AS top1,
                    COUNT(*) FILTER (WHERE rang = 2) AS top2,
                    COUNT(*) FILTER (WHERE rang = 3) AS top3,
                    AVG(score) AS avg_score
                FROM ranked
                GROUP BY canal
                ORDER BY
                    COUNT(*) FILTER (WHERE rang = 1) DESC,
                    COUNT(*) FILTER (WHERE rang = 2) DESC,
                    canal
                """,
                score_params * 3,
            )
            top3_distribution = [dict(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                WITH filtered AS (
                    SELECT
                        COALESCE(s.region, 'Non renseignée') AS region,
                        s.canal_top1,
                        s.score_top1
                    FROM dm_best_channel_scores s
                    WHERE {score_where_sql}
                ),
                region_summary AS (
                    SELECT
                        region,
                        COUNT(*) AS clients_scores,
                        AVG(score_top1) AS avg_top1_score
                    FROM filtered
                    GROUP BY region
                ),
                channel_counts AS (
                    SELECT
                        region,
                        canal_top1,
                        COUNT(*) AS channel_clients,
                        ROW_NUMBER() OVER (
                            PARTITION BY region
                            ORDER BY COUNT(*) DESC, canal_top1
                        ) AS rn
                    FROM filtered
                    GROUP BY region, canal_top1
                )
                SELECT
                    r.region,
                    r.clients_scores,
                    r.avg_top1_score,
                    c.canal_top1 AS dominant_channel,
                    c.channel_clients AS dominant_clients
                FROM region_summary r
                LEFT JOIN channel_counts c
                  ON c.region = r.region
                 AND c.rn = 1
                ORDER BY r.clients_scores DESC, r.region
                """,
                score_params,
            )
            regions = [dict(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                WITH sequences AS (
                    SELECT
                        i.id_campagne,
                        i.radical_compte,
                        i.sequence_no,
                        MAX(i.objectif_valide) AS objectif_valide,
                        MAX(i.source) AS source
                    FROM dm_best_channel_interactions i
                    WHERE {interaction_where_sql}
                    GROUP BY i.id_campagne, i.radical_compte, i.sequence_no
                )
                SELECT
                    COUNT(*) AS sequences,
                    COUNT(*) FILTER (WHERE objectif_valide = 1) AS converted_sequences,
                    COUNT(*) FILTER (WHERE source = 'fake') AS fake_sequences,
                    COUNT(*) FILTER (WHERE source = 'reel') AS real_sequences
                FROM sequences
                """,
                interaction_params,
            )
            sequence_summary = dict(cur.fetchone() or {})

            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS interaction_rows,
                    COUNT(*) FILTER (WHERE i.source = 'fake') AS fake_rows,
                    COUNT(*) FILTER (WHERE i.source = 'reel') AS real_rows,
                    MIN(i.observed_at) AS observed_min,
                    MAX(i.observed_at) AS observed_max
                FROM dm_best_channel_interactions i
                WHERE {interaction_where_sql}
                """,
                interaction_params,
            )
            interaction_summary = dict(cur.fetchone() or {})

    scored_clients = _as_int(score_summary.get("scored_clients"))
    non_scored = _as_int(score_summary.get("non_scored"))
    sequences = _as_int(sequence_summary.get("sequences"))
    converted_sequences = _as_int(sequence_summary.get("converted_sequences"))

    metadata = load_metadata() if model_exists() else {}
    summary = {
        "scored_clients": scored_clients,
        "non_scored": non_scored,
        "avg_top1_score": _as_float(score_summary.get("avg_top1_score")),
        "max_top1_score": _as_float(score_summary.get("max_top1_score")),
        "last_scoring": (
            score_summary.get("last_scoring").isoformat()
            if score_summary.get("last_scoring") is not None
            else None
        ),
        "sequences": sequences,
        "converted_sequences": converted_sequences,
        "conversion_rate": (converted_sequences / sequences * 100.0) if sequences else 0.0,
    }

    training = {
        "interaction_rows": _as_int(interaction_summary.get("interaction_rows")),
        "fake_rows": _as_int(interaction_summary.get("fake_rows")),
        "real_rows": _as_int(interaction_summary.get("real_rows")),
        "sequences": sequences,
        "converted_sequences": converted_sequences,
        "fake_sequences": _as_int(sequence_summary.get("fake_sequences")),
        "real_sequences": _as_int(sequence_summary.get("real_sequences")),
        "observed_min": (
            interaction_summary.get("observed_min").isoformat()
            if interaction_summary.get("observed_min") is not None
            else None
        ),
        "observed_max": (
            interaction_summary.get("observed_max").isoformat()
            if interaction_summary.get("observed_max") is not None
            else None
        ),
    }

    return {
        "filters": {"annee_mois": month, "region": region, "statut_client": statut_client},
        "summary": summary,
        "top1_distribution": top1_distribution,
        "top3_distribution": top3_distribution,
        "regions": regions,
        "training": training,
        "model": {
            "exists": model_exists(),
            "model_code": metadata.get("model_code"),
            "trained_at": metadata.get("trained_at"),
            "training_rows": metadata.get("training_rows"),
            "validation_rows": metadata.get("validation_rows"),
            "positive_rows": metadata.get("positive_rows"),
            "validation_auc": metadata.get("validation_auc"),
            "best_iteration": metadata.get("best_iteration"),
        },
    }
