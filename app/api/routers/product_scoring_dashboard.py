from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from app.product_scoring.constants import CARD_PRODUCTS, PRODUCT_LABELS
from app.product_scoring.model import dashboard_model_metadata
from app.storage.postgres_db import connection

router = APIRouter()


def _latest_month() -> int | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(annee_mois) FROM dm_product_scores")
            row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _to_float(value: Any) -> float:
    return float(value or 0.0)


def _to_int(value: Any) -> int:
    return int(value or 0)


@router.get("/data-tools/product-scoring/filters")
def product_scoring_filters() -> Dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT annee_mois FROM dm_product_scores ORDER BY annee_mois DESC")
            months = [int(row[0]) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT DISTINCT region
                FROM dm_product_scores
                WHERE region IS NOT NULL AND BTRIM(region) <> ''
                ORDER BY region
                """
            )
            regions = [str(row[0]) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT DISTINCT statut_client_snapshot
                FROM dm_product_scores
                WHERE statut_client_snapshot IS NOT NULL AND BTRIM(statut_client_snapshot) <> ''
                ORDER BY statut_client_snapshot
                """
            )
            statuses = [str(row[0]) for row in cur.fetchall()]
    return {
        "months": months,
        "default_annee_mois": months[0] if months else None,
        "regions": regions,
        "statuses": statuses,
        "products": list(PRODUCT_LABELS.values()),
        "cards": list(CARD_PRODUCTS),
    }


@router.get("/data-tools/product-scoring/dashboard")
def product_scoring_dashboard(
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
            "next_best_product": [],
            "card_recommendations": [],
            "credit_segments": {"conso": [], "immo": []},
            "regions": [],
            "models": dashboard_model_metadata(),
            "feedback": {},
        }

    where = ["s.annee_mois = %s"]
    params: List[Any] = [month]
    if region:
        where.append("s.region = %s")
        params.append(region)
    if statut_client:
        where.append("s.statut_client_snapshot = %s")
        params.append(statut_client)
    where_sql = " AND ".join(where)

    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS scored_clients,
                    AVG(s.appetence_carte) AS avg_card,
                    AVG(s.appetence_conso) AS avg_conso,
                    AVG(s.appetence_immo) AS avg_immo,
                    AVG(s.appetence_epargne) AS avg_epargne,
                    AVG(s.next_best_product_score) AS avg_nbp_score,
                    COUNT(*) FILTER (WHERE s.appetence_carte IS NOT NULL) AS card_eligible_clients,
                    COUNT(*) FILTER (WHERE s.appetence_epargne IS NOT NULL) AS epargne_eligible_clients,
                    MAX(s.date_scoring) AS last_scoring
                FROM dm_product_scores s
                WHERE {where_sql}
                """,
                params,
            )
            summary = dict(cur.fetchone() or {})

            cur.execute(
                f"""
                SELECT s.next_best_product AS product, COUNT(*) AS clients,
                       AVG(s.next_best_product_score) AS avg_score
                FROM dm_product_scores s
                WHERE {where_sql}
                GROUP BY s.next_best_product
                ORDER BY clients DESC, product
                """,
                params,
            )
            nbp = [dict(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                SELECT s.carte_recommandee AS card, COUNT(*) AS clients,
                       AVG(s.appetence_carte) AS avg_score
                FROM dm_product_scores s
                WHERE {where_sql}
                  AND s.carte_recommandee <> 'non_score'
                GROUP BY s.carte_recommandee
                ORDER BY clients DESC, card
                """,
                params,
            )
            cards = [dict(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                SELECT s.conso_model_segment AS segment, COUNT(*) AS clients,
                       AVG(s.appetence_conso) AS avg_score
                FROM dm_product_scores s
                WHERE {where_sql}
                GROUP BY s.conso_model_segment
                ORDER BY clients DESC, segment
                """,
                params,
            )
            conso_segments = [dict(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                SELECT s.immo_model_segment AS segment, COUNT(*) AS clients,
                       AVG(s.appetence_immo) AS avg_score
                FROM dm_product_scores s
                WHERE {where_sql}
                GROUP BY s.immo_model_segment
                ORDER BY clients DESC, segment
                """,
                params,
            )
            immo_segments = [dict(row) for row in cur.fetchall()]

            # La sous-requête choisit le NBP dominant par région sans dépendre
            # d'une fonction PostgreSQL non standard comme mode().
            cur.execute(
                f"""
                WITH base AS (
                    SELECT s.*
                    FROM dm_product_scores s
                    WHERE {where_sql}
                ), ranked AS (
                    SELECT region, next_best_product, COUNT(*) AS n,
                           ROW_NUMBER() OVER (
                               PARTITION BY COALESCE(region, 'Non renseignée')
                               ORDER BY COUNT(*) DESC, next_best_product
                           ) AS rn
                    FROM base
                    GROUP BY region, next_best_product
                )
                SELECT COALESCE(b.region, 'Non renseignée') AS region,
                       COUNT(*) AS clients,
                       AVG(b.appetence_carte) AS avg_card,
                       AVG(b.appetence_conso) AS avg_conso,
                       AVG(b.appetence_immo) AS avg_immo,
                       AVG(b.appetence_epargne) AS avg_epargne,
                       COALESCE(MAX(r.next_best_product) FILTER (WHERE r.rn=1), 'non_score') AS dominant_product
                FROM base b
                LEFT JOIN ranked r
                  ON r.region IS NOT DISTINCT FROM b.region AND r.rn=1
                GROUP BY COALESCE(b.region, 'Non renseignée')
                ORDER BY clients DESC, region
                """,
                params,
            )
            region_rows = [dict(row) for row in cur.fetchall()]

            # Le feedback est relié au score effectivement utilisé au lancement.
            feedback_where = ["s.annee_mois = %s"]
            feedback_params: List[Any] = [month]
            if region:
                feedback_where.append("s.region = %s")
                feedback_params.append(region)
            if statut_client:
                feedback_where.append("s.statut_client_snapshot = %s")
                feedback_params.append(statut_client)
            cur.execute(
                f"""
                SELECT
                    COUNT(f.id) AS assignments,
                    COUNT(f.id) FILTER (WHERE f.was_contacted) AS contacted,
                    COUNT(f.id) FILTER (WHERE f.objective_achieved IS NOT NULL) AS resolved,
                    COUNT(f.id) FILTER (WHERE f.objective_achieved = 1) AS conversions,
                    COUNT(f.id) FILTER (WHERE f.appetent_at_launch AND f.was_contacted) AS appetent_assignments
                FROM dm_product_scores s
                LEFT JOIN dm_product_campaign_feedback f ON f.score_id = s.id
                WHERE {' AND '.join(feedback_where)}
                """,
                feedback_params,
            )
            feedback = dict(cur.fetchone() or {})

    for key in ("scored_clients", "card_eligible_clients", "epargne_eligible_clients"):
        summary[key] = _to_int(summary.get(key))
    for key in ("avg_card", "avg_conso", "avg_immo", "avg_epargne", "avg_nbp_score"):
        summary[key] = _to_float(summary.get(key))

    for rows in (nbp, cards, conso_segments, immo_segments):
        for row in rows:
            row["clients"] = _to_int(row.get("clients"))
            row["avg_score"] = _to_float(row.get("avg_score"))

    for row in region_rows:
        row["clients"] = _to_int(row.get("clients"))
        for key in ("avg_card", "avg_conso", "avg_immo", "avg_epargne"):
            row[key] = _to_float(row.get(key))

    for key in ("assignments", "contacted", "resolved", "conversions", "appetent_assignments"):
        feedback[key] = _to_int(feedback.get(key))
    resolved = feedback["resolved"]
    feedback["conversion_rate"] = (feedback["conversions"] / resolved * 100.0) if resolved else 0.0

    models = dashboard_model_metadata()
    for model in models:
        if model.get("validation_auc") is not None:
            model["validation_auc"] = float(model["validation_auc"])
        model["training_rows"] = _to_int(model.get("training_rows"))
        model["positive_rows"] = _to_int(model.get("positive_rows"))

    return {
        "filters": {"annee_mois": month, "region": region, "statut_client": statut_client},
        "summary": summary,
        "next_best_product": nbp,
        "card_recommendations": cards,
        "credit_segments": {"conso": conso_segments, "immo": immo_segments},
        "regions": region_rows,
        "models": models,
        "feedback": feedback,
    }
