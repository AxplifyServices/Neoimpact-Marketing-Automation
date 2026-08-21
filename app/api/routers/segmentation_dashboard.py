from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.storage.postgres_db import connection

router = APIRouter()

AGE_ORDER = ["0-17", "18-24", "25-34", "35-49", "50-60", "60+"]
SEGMENT_ORDER = ["Mass Market", "Medium", "Haut de gamme", "Premium", "Banque privée"]


def _age_sort_key(value: str) -> int:
    try:
        return AGE_ORDER.index(value)
    except ValueError:
        return len(AGE_ORDER)


def _as_float(value: Any) -> float:
    return 0.0 if value is None else float(value)


def _as_int(value: Any) -> int:
    return 0 if value is None else int(value)


@router.get("/data-tools/segmentation/filters")
def segmentation_filters() -> Dict[str, Any]:
    """Filtres réellement disponibles dans l'historique de segmentation."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT annee_mois FROM dm_segmentation_resultats ORDER BY annee_mois DESC"
            )
            months = [int(row[0]) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT DISTINCT region
                FROM dm_segmentation_resultats
                WHERE region IS NOT NULL AND BTRIM(region) <> ''
                ORDER BY region
                """
            )
            regions = [str(row[0]) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT DISTINCT tranche_age
                FROM dm_segmentation_resultats
                WHERE tranche_age IS NOT NULL AND BTRIM(tranche_age) <> ''
                """
            )
            age_bands = sorted([str(row[0]) for row in cur.fetchall()], key=_age_sort_key)

    return {
        "annee_mois": months,
        "default_annee_mois": months[0] if months else None,
        "regions": regions,
        "tranches_age": age_bands,
    }


@router.get("/data-tools/segmentation/dashboard")
def segmentation_dashboard(
    annee_mois: int = Query(..., ge=190001, le=299912),
    region: Optional[str] = Query(default=None, max_length=150),
    tranche_age: Optional[str] = Query(default=None, max_length=30),
) -> Dict[str, Any]:
    """
    Tableau de bord de segmentation.

    La répartition et les KPI utilisent le dernier résultat connu de chaque
    client au plus tard à la période choisie. Les médianes sont celles
    réellement calculées et archivées pendant la période sélectionnée.
    """
    region = (region or "").strip() or None
    tranche_age = (tranche_age or "").strip() or None

    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM dm_segmentation_resultats WHERE annee_mois = %s) AS ok",
                (annee_mois,),
            )
            if not bool((cur.fetchone() or {}).get("ok")):
                raise HTTPException(
                    status_code=404,
                    detail=f"Aucun résultat de segmentation pour la période {annee_mois}.",
                )

            cur.execute("DROP TABLE IF EXISTS tmp_segmentation_dashboard_latest")
            cur.execute(
                """
                CREATE TEMP TABLE tmp_segmentation_dashboard_latest
                ON COMMIT DROP
                AS
                SELECT DISTINCT ON (r.radical_compte)
                    r.radical_compte,
                    r.annee_mois,
                    r.date_segmentation,
                    r.age,
                    r.tranche_age,
                    r.region,
                    r.statut_salarie,
                    r.freq_prop,
                    r.flux_crediteur_moy_3m,
                    r.encours_selon_statut,
                    r.segment
                FROM dm_segmentation_resultats AS r
                WHERE r.annee_mois <= %s
                  AND r.segment <> 'Non segmenté'
                ORDER BY r.radical_compte, r.annee_mois DESC
                """,
                (annee_mois,),
            )
            cur.execute("CREATE INDEX ON tmp_segmentation_dashboard_latest (region, tranche_age)")
            cur.execute("ANALYZE tmp_segmentation_dashboard_latest")

            where_parts: List[str] = []
            params: List[Any] = []
            if region:
                where_parts.append("region = %s")
                params.append(region)
            if tranche_age:
                where_parts.append("tranche_age = %s")
                params.append(tranche_age)
            where_sql = " WHERE " + " AND ".join(where_parts) if where_parts else ""

            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS clients_segmentes,
                    COUNT(*) FILTER (WHERE statut_salarie = 'Salarié') AS clients_salaries,
                    AVG(flux_crediteur_moy_3m) AS flux_moyen_3m,
                    AVG(encours_selon_statut) AS avoir_moyen_3m,
                    AVG(freq_prop) AS frequence_flux_moyenne,
                    COUNT(*) FILTER (
                        WHERE segment IN ('Haut de gamme', 'Premium', 'Banque privée')
                    ) AS clients_haut_potentiel
                FROM tmp_segmentation_dashboard_latest
                {where_sql}
                """,
                params,
            )
            kpi_row = dict(cur.fetchone() or {})
            total = _as_int(kpi_row.get("clients_segmentes"))
            salaries = _as_int(kpi_row.get("clients_salaries"))
            high_value = _as_int(kpi_row.get("clients_haut_potentiel"))

            cur.execute(
                f"""
                SELECT segment, COUNT(*) AS clients
                FROM tmp_segmentation_dashboard_latest
                {where_sql}
                GROUP BY segment
                """,
                params,
            )
            segment_counts = {
                str(row["segment"]): _as_int(row["clients"])
                for row in cur.fetchall()
            }
            segment_distribution = [
                {
                    "segment": segment,
                    "clients": segment_counts.get(segment, 0),
                    "part": (segment_counts.get(segment, 0) / total * 100.0) if total else 0.0,
                }
                for segment in SEGMENT_ORDER
            ]

            cur.execute(
                f"""
                SELECT statut_salarie, COUNT(*) AS clients
                FROM tmp_segmentation_dashboard_latest
                {where_sql}
                GROUP BY statut_salarie
                ORDER BY clients DESC
                """,
                params,
            )
            salary_distribution = [
                {
                    "statut": str(row["statut_salarie"] or "Non renseigné"),
                    "clients": _as_int(row["clients"]),
                }
                for row in cur.fetchall()
            ]

            period_where = ["annee_mois = %s", "segment <> 'Non segmenté'"]
            period_params: List[Any] = [annee_mois]
            if region:
                period_where.append("region = %s")
                period_params.append(region)
            if tranche_age:
                period_where.append("tranche_age = %s")
                period_params.append(tranche_age)
            period_where_sql = " AND ".join(period_where)

            cur.execute(
                f"""
                SELECT
                    region,
                    tranche_age,
                    MAX(mediane_flux)::DOUBLE PRECISION AS mediane_flux,
                    MAX(mediane_avoirs)::DOUBLE PRECISION AS mediane_avoirs,
                    COUNT(*) AS observations
                FROM dm_segmentation_resultats
                WHERE {period_where_sql}
                  AND mediane_flux IS NOT NULL
                  AND mediane_avoirs IS NOT NULL
                GROUP BY region, tranche_age
                ORDER BY region, tranche_age
                """,
                period_params,
            )
            medians = [
                {
                    "region": str(row["region"] or ""),
                    "tranche_age": str(row["tranche_age"] or ""),
                    "mediane_flux": _as_float(row["mediane_flux"]),
                    "mediane_avoirs": _as_float(row["mediane_avoirs"]),
                    "observations": _as_int(row["observations"]),
                }
                for row in cur.fetchall()
            ]
            medians.sort(key=lambda item: (item["region"], _age_sort_key(item["tranche_age"])))

            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS calculs_periode,
                    MAX(date_segmentation) AS derniere_date_segmentation
                FROM dm_segmentation_resultats
                WHERE {period_where_sql}
                """,
                period_params,
            )
            period_row = dict(cur.fetchone() or {})

    return {
        "filters": {
            "annee_mois": annee_mois,
            "region": region,
            "tranche_age": tranche_age,
        },
        "kpis": {
            "clients_segmentes": total,
            "taux_salaries": (salaries / total * 100.0) if total else 0.0,
            "flux_moyen_3m": _as_float(kpi_row.get("flux_moyen_3m")),
            "avoir_moyen_3m": _as_float(kpi_row.get("avoir_moyen_3m")),
            "frequence_flux_moyenne": _as_float(kpi_row.get("frequence_flux_moyenne")),
            "taux_haut_potentiel": (high_value / total * 100.0) if total else 0.0,
            "calculs_periode": _as_int(period_row.get("calculs_periode")),
            "derniere_date_segmentation": (
                str(period_row.get("derniere_date_segmentation"))
                if period_row.get("derniere_date_segmentation")
                else None
            ),
        },
        "segments": segment_distribution,
        "statuts_salarie": salary_distribution,
        "medianes": medians,
    }
