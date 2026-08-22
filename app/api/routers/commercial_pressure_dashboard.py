from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from app.commercial_pressure.scoring import PRESSURE_LEVELS
from app.storage.postgres_db import connection

router = APIRouter()


def _latest_month() -> int | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(annee_mois) FROM dm_commercial_pressure_scores")
            row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else None


@router.get("/data-tools/commercial-pressure/filters")
def commercial_pressure_filters() -> Dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT annee_mois FROM dm_commercial_pressure_scores ORDER BY annee_mois DESC")
            months = [int(row[0]) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT DISTINCT region
                FROM dm_commercial_pressure_scores
                WHERE region IS NOT NULL AND BTRIM(region) <> ''
                ORDER BY region
                """
            )
            regions = [str(row[0]) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT DISTINCT statut_client_snapshot
                FROM dm_commercial_pressure_scores
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
        "levels": PRESSURE_LEVELS,
    }


@router.get("/data-tools/commercial-pressure/dashboard")
def commercial_pressure_dashboard(
    annee_mois: Optional[int] = Query(default=None, ge=190001, le=299912),
    region: Optional[str] = Query(default=None, max_length=150),
    statut_client: Optional[str] = Query(default=None, max_length=80),
    niveau: Optional[str] = Query(default=None, max_length=30),
) -> Dict[str, Any]:
    month = int(annee_mois or (_latest_month() or 0))
    region = (region or "").strip() or None
    statut_client = (statut_client or "").strip() or None
    niveau = (niveau or "").strip() or None

    if month <= 0:
        return {
            "filters": {"annee_mois": None, "region": region, "statut_client": statut_client, "niveau": niveau},
            "summary": {},
            "distribution": [],
            "regions": [],
            "rules": [],
        }

    where = ["s.annee_mois = %s"]
    params: List[Any] = [month]
    if region:
        where.append("s.region = %s")
        params.append(region)
    if statut_client:
        where.append("s.statut_client_snapshot = %s")
        params.append(statut_client)
    if niveau:
        where.append("s.niveau_pression = %s")
        params.append(niveau)
    where_sql = " AND ".join(where)

    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS scored_clients,
                    COUNT(*) FILTER (WHERE s.niveau_pression = 'Eleve') AS high_clients,
                    AVG(s.score_pression) AS avg_score,
                    AVG(s.nb_actions_7j) AS avg_actions_7d,
                    AVG(s.nb_actions_30j) AS avg_actions_30d,
                    AVG(s.nb_canaux_7j) AS avg_channels_7d,
                    MAX(s.date_scoring) AS last_scoring
                FROM dm_commercial_pressure_scores s
                WHERE {where_sql}
                """,
                params,
            )
            summary = dict(cur.fetchone() or {})

            cur.execute(
                f"""
                SELECT s.niveau_pression AS niveau,
                       COUNT(*) AS clients,
                       AVG(s.score_pression) AS avg_score,
                       AVG(s.nb_actions_30j) AS avg_actions_30d
                FROM dm_commercial_pressure_scores s
                WHERE {where_sql}
                GROUP BY s.niveau_pression
                ORDER BY CASE s.niveau_pression
                    WHEN 'Eleve' THEN 1 WHEN 'Modere' THEN 2 ELSE 3 END
                """,
                params,
            )
            distribution = [dict(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                SELECT COALESCE(s.region, 'Non renseignée') AS region,
                       COUNT(*) AS clients,
                       COUNT(*) FILTER (WHERE s.niveau_pression = 'Eleve') AS high_clients,
                       AVG(s.score_pression) AS avg_score,
                       AVG(s.nb_actions_30j) AS avg_actions_30d
                FROM dm_commercial_pressure_scores s
                WHERE {where_sql}
                GROUP BY COALESCE(s.region, 'Non renseignée')
                ORDER BY high_clients DESC, clients DESC, region
                """,
                params,
            )
            regions = [dict(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                SELECT s.regle_niveau AS regle,
                       COUNT(*) AS clients
                FROM dm_commercial_pressure_scores s
                WHERE {where_sql}
                  AND s.niveau_pression IN ('Modere', 'Eleve')
                GROUP BY s.regle_niveau
                ORDER BY clients DESC, regle
                """,
                params,
            )
            rules = [dict(row) for row in cur.fetchall()]

    scored = int(summary.get("scored_clients") or 0)
    high = int(summary.get("high_clients") or 0)
    summary["scored_clients"] = scored
    summary["high_clients"] = high
    summary["high_rate"] = (high / scored * 100.0) if scored else 0.0
    for key in ("avg_score", "avg_actions_7d", "avg_actions_30d", "avg_channels_7d"):
        summary[key] = float(summary.get(key) or 0.0)

    for row in distribution:
        row["clients"] = int(row.get("clients") or 0)
        row["avg_score"] = float(row.get("avg_score") or 0.0)
        row["avg_actions_30d"] = float(row.get("avg_actions_30d") or 0.0)
    for row in regions:
        row["clients"] = int(row.get("clients") or 0)
        row["high_clients"] = int(row.get("high_clients") or 0)
        row["high_rate"] = (row["high_clients"] / row["clients"] * 100.0) if row["clients"] else 0.0
        row["avg_score"] = float(row.get("avg_score") or 0.0)
        row["avg_actions_30d"] = float(row.get("avg_actions_30d") or 0.0)
    for row in rules:
        row["clients"] = int(row.get("clients") or 0)

    return {
        "filters": {"annee_mois": month, "region": region, "statut_client": statut_client, "niveau": niveau},
        "summary": summary,
        "distribution": distribution,
        "regions": regions,
        "rules": rules,
        "thresholds": {
            "low_max": 4.0,
            "moderate_max": 8.0,
            "high_actions_7d": 6,
            "high_actions_30d": 10,
            "high_human_7d": 4,
            "high_channels_7d": 4,
            "moderate_actions_7d": 4,
        },
    }
