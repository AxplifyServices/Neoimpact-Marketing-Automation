from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query

from app.storage.postgres_db import connection

router = APIRouter()


def _latest_month() -> int | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(annee_mois) FROM dm_engagement_digital_resultats")
            row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else None


@router.get("/data-tools/digital-engagement/filters")
def digital_engagement_filters():
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT annee_mois
                FROM dm_engagement_digital_resultats
                ORDER BY annee_mois DESC
                """
            )
            months = [int(row[0]) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT DISTINCT region
                FROM dm_engagement_digital_resultats
                WHERE region IS NOT NULL AND BTRIM(region) <> ''
                ORDER BY region
                """
            )
            regions = [str(row[0]) for row in cur.fetchall()]

    return {
        "months": months,
        "regions": regions,
        "statuses": ["Actif", "Inactif"],
        "engagements": ["Faible", "Modere", "Eleve"],
        "creneaux": ["Matin", "Apres-midi", "Soir", "non_score"],
    }


@router.get("/data-tools/digital-engagement/dashboard")
def digital_engagement_dashboard(
    annee_mois: Optional[int] = Query(default=None),
    region: Optional[str] = Query(default=None, max_length=120),
    statut_client: Optional[str] = Query(default=None, max_length=40),
):
    month = int(annee_mois or (_latest_month() or 0))
    if month <= 0:
        return {
            "annee_mois": None,
            "summary": {},
            "engagement_distribution": [],
            "creneau_distribution": [],
            "regions": [],
        }

    where = ["r.annee_mois = %s"]
    params: list[Any] = [month]
    if region and region.strip():
        where.append("r.region = %s")
        params.append(region.strip())
    if statut_client and statut_client.strip():
        where.append("LOWER(BTRIM(COALESCE(r.statut_client_snapshot, ''))) = LOWER(%s)")
        params.append(statut_client.strip())
    where_sql = " AND ".join(where)

    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS scored_clients,
                    COUNT(*) FILTER (WHERE r.engagement_digital = 'Eleve') AS high_clients,
                    AVG(r.moyenne_connexions_jour) AS avg_daily_connections,
                    MAX(r.mediane_connexions_jour) AS median_daily_connections,
                    AVG(r.heure_moyenne_ponderee) FILTER (
                        WHERE r.heure_moyenne_ponderee IS NOT NULL
                    ) AS avg_weighted_hour
                FROM dm_engagement_digital_resultats AS r
                WHERE {where_sql}
                """,
                params,
            )
            summary_row = dict(cur.fetchone() or {})

            cur.execute(
                f"""
                SELECT
                    r.engagement_digital AS label,
                    COUNT(*) AS clients
                FROM dm_engagement_digital_resultats AS r
                WHERE {where_sql}
                GROUP BY r.engagement_digital
                ORDER BY CASE r.engagement_digital
                    WHEN 'Faible' THEN 1
                    WHEN 'Modere' THEN 2
                    WHEN 'Eleve' THEN 3
                    ELSE 4
                END
                """,
                params,
            )
            engagement_distribution = [dict(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                SELECT
                    r.creneau_connexion AS label,
                    COUNT(*) AS clients
                FROM dm_engagement_digital_resultats AS r
                WHERE {where_sql}
                GROUP BY r.creneau_connexion
                ORDER BY CASE r.creneau_connexion
                    WHEN 'Matin' THEN 1
                    WHEN 'Apres-midi' THEN 2
                    WHEN 'Soir' THEN 3
                    ELSE 4
                END
                """,
                params,
            )
            creneau_distribution = [dict(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                SELECT
                    COALESCE(r.region, 'Non renseignée') AS region,
                    COUNT(*) AS clients,
                    COUNT(*) FILTER (WHERE r.engagement_digital = 'Eleve') AS high_clients,
                    AVG(r.moyenne_connexions_jour) AS avg_daily_connections
                FROM dm_engagement_digital_resultats AS r
                WHERE {where_sql}
                GROUP BY COALESCE(r.region, 'Non renseignée')
                ORDER BY clients DESC, region
                """,
                params,
            )
            regions = [dict(row) for row in cur.fetchall()]

    scored = int(summary_row.get("scored_clients") or 0)
    high = int(summary_row.get("high_clients") or 0)
    summary = {
        "scored_clients": scored,
        "high_clients": high,
        "high_rate": (high / scored * 100.0) if scored else 0.0,
        "avg_daily_connections": float(summary_row.get("avg_daily_connections") or 0.0),
        "median_daily_connections": float(summary_row.get("median_daily_connections") or 0.0),
        "avg_weighted_hour": (
            float(summary_row["avg_weighted_hour"])
            if summary_row.get("avg_weighted_hour") is not None
            else None
        ),
    }

    return {
        "annee_mois": month,
        "summary": summary,
        "engagement_distribution": engagement_distribution,
        "creneau_distribution": creneau_distribution,
        "regions": regions,
    }
