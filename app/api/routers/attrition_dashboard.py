from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.attrition.model import load_metadata, model_exists
from app.storage.postgres_db import connection

router = APIRouter()


def _as_int(value: Any) -> int:
    return 0 if value is None else int(value)


def _as_float(value: Any) -> float:
    return 0.0 if value is None else float(value)


@router.get("/data-tools/attrition/filters")
def attrition_filters() -> Dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT annee_mois FROM dm_attrition_scores ORDER BY annee_mois DESC")
            months = [int(row[0]) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT DISTINCT region
                FROM dm_attrition_scores
                WHERE region IS NOT NULL AND BTRIM(region) <> ''
                ORDER BY region
                """
            )
            regions = [str(row[0]) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT DISTINCT statut_client_snapshot
                FROM dm_attrition_scores
                WHERE statut_client_snapshot IS NOT NULL AND BTRIM(statut_client_snapshot) <> ''
                ORDER BY statut_client_snapshot
                """
            )
            statuses = [str(row[0]) for row in cur.fetchall()]
    return {
        "annee_mois": months,
        "default_annee_mois": months[0] if months else None,
        "regions": regions,
        "statuts": statuses,
    }


@router.get("/data-tools/attrition/dashboard")
def attrition_dashboard(
    annee_mois: int = Query(..., ge=190001, le=299912),
    region: Optional[str] = Query(default=None, max_length=150),
    statut: Optional[str] = Query(default=None, max_length=80),
) -> Dict[str, Any]:
    region = (region or "").strip() or None
    statut = (statut or "").strip() or None

    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM dm_attrition_scores WHERE annee_mois = %s) AS ok",
                (annee_mois,),
            )
            if not bool((cur.fetchone() or {}).get("ok")):
                raise HTTPException(status_code=404, detail=f"Aucun scoring attrition pour {annee_mois}.")

            where = ["s.annee_mois = %s"]
            params: List[Any] = [annee_mois]
            if region:
                where.append("s.region = %s")
                params.append(region)
            if statut:
                where.append("s.statut_client_snapshot = %s")
                params.append(statut)
            where_sql = " AND ".join(where)

            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS clients_scores,
                    COUNT(*) FILTER (WHERE s.risque_attrition = 'Oui') AS clients_risque,
                    AVG(s.score_attrition) AS score_moyen,
                    AVG(s.score_attrition) FILTER (WHERE s.risque_attrition = 'Oui') AS score_moyen_risque,
                    MAX(s.seuil_risque) AS seuil_risque,
                    MAX(s.date_scoring) AS date_scoring
                FROM dm_attrition_scores AS s
                WHERE {where_sql}
                """,
                params,
            )
            kpi = dict(cur.fetchone() or {})
            total = _as_int(kpi.get("clients_scores"))
            at_risk = _as_int(kpi.get("clients_risque"))

            cur.execute(
                f"""
                SELECT s.risque_attrition, COUNT(*) AS clients
                FROM dm_attrition_scores AS s
                WHERE {where_sql}
                GROUP BY s.risque_attrition
                ORDER BY s.risque_attrition DESC
                """,
                params,
            )
            risk_distribution = [
                {"risque": str(row["risque_attrition"]), "clients": _as_int(row["clients"])}
                for row in cur.fetchall()
            ]

            cur.execute(
                f"""
                SELECT
                    CASE
                        WHEN s.score_attrition < 0.2 THEN '0-20%%'
                        WHEN s.score_attrition < 0.4 THEN '20-40%%'
                        WHEN s.score_attrition < 0.6 THEN '40-60%%'
                        WHEN s.score_attrition < 0.8 THEN '60-80%%'
                        ELSE '80-100%%'
                    END AS tranche,
                    COUNT(*) AS clients
                FROM dm_attrition_scores AS s
                WHERE {where_sql}
                GROUP BY tranche
                """,
                params,
            )
            bands_map = {str(row["tranche"]): _as_int(row["clients"]) for row in cur.fetchall()}
            score_bands = [
                {"tranche": label, "clients": bands_map.get(label, 0)}
                for label in ["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"]
            ]

            cur.execute(
                f"""
                SELECT
                    s.region,
                    COUNT(*) AS clients_scores,
                    COUNT(*) FILTER (WHERE s.risque_attrition = 'Oui') AS clients_risque,
                    AVG(s.score_attrition) AS score_moyen
                FROM dm_attrition_scores AS s
                WHERE {where_sql}
                  AND s.region IS NOT NULL
                GROUP BY s.region
                ORDER BY clients_risque DESC, clients_scores DESC
                LIMIT 20
                """,
                params,
            )
            regions = []
            for row in cur.fetchall():
                row_total = _as_int(row["clients_scores"])
                row_risk = _as_int(row["clients_risque"])
                regions.append({
                    "region": str(row["region"] or ""),
                    "clients_scores": row_total,
                    "clients_risque": row_risk,
                    "taux_risque": (row_risk / row_total * 100.0) if row_total else 0.0,
                    "score_moyen": _as_float(row["score_moyen"]),
                })

            # Variations qui expliquent le signal : moyenne sur les clients flaggés.
            cur.execute(
                f"""
                SELECT
                    AVG(v.var_avoirs_1m) AS avoirs_1m,
                    AVG(v.var_avoirs_3m) AS avoirs_3m,
                    AVG(v.var_avoirs_6m) AS avoirs_6m,
                    AVG(v.var_avoirs_12m) AS avoirs_12m,
                    AVG(v.var_flux_crediteurs_1m) AS credits_1m,
                    AVG(v.var_flux_crediteurs_3m) AS credits_3m,
                    AVG(v.var_flux_crediteurs_6m) AS credits_6m,
                    AVG(v.var_flux_crediteurs_12m) AS credits_12m,
                    AVG(v.var_flux_debiteurs_1m) AS debits_1m,
                    AVG(v.var_flux_debiteurs_3m) AS debits_3m,
                    AVG(v.var_flux_debiteurs_6m) AS debits_6m,
                    AVG(v.var_flux_debiteurs_12m) AS debits_12m
                FROM dm_attrition_scores AS s
                JOIN dm_attrition_variables AS v
                  ON v.radical_compte = s.radical_compte
                 AND v.annee_mois = s.annee_mois
                WHERE {where_sql}
                  AND s.risque_attrition = 'Oui'
                """,
                params,
            )
            variation_row = dict(cur.fetchone() or {})

            cur.execute(
                """
                SELECT
                    COUNT(*) AS training_rows,
                    COUNT(*) FILTER (WHERE attrition = 1) AS attritions_observees,
                    MIN(annee_mois) AS mois_min,
                    MAX(annee_mois) AS mois_max
                FROM dm_attrition_variables
                """
            )
            training = dict(cur.fetchone() or {})

    metadata = load_metadata() if model_exists() else {}
    return {
        "filters": {"annee_mois": annee_mois, "region": region, "statut": statut},
        "kpis": {
            "clients_scores": total,
            "clients_risque": at_risk,
            "taux_risque": (at_risk / total * 100.0) if total else 0.0,
            "score_moyen": _as_float(kpi.get("score_moyen")),
            "score_moyen_risque": _as_float(kpi.get("score_moyen_risque")),
            "seuil_risque": _as_float(kpi.get("seuil_risque")),
            "date_scoring": str(kpi.get("date_scoring")) if kpi.get("date_scoring") else None,
        },
        "risk_distribution": risk_distribution,
        "score_bands": score_bands,
        "regions": regions,
        "variations_risque": {
            "avoirs": [_as_float(variation_row.get(f"avoirs_{h}m")) for h in (1, 3, 6, 12)],
            "flux_crediteurs": [_as_float(variation_row.get(f"credits_{h}m")) for h in (1, 3, 6, 12)],
            "flux_debiteurs": [_as_float(variation_row.get(f"debits_{h}m")) for h in (1, 3, 6, 12)],
            "horizons": ["1 mois", "3 mois", "6 mois", "12 mois"],
        },
        "training": {
            "rows": _as_int(training.get("training_rows")),
            "attritions_observees": _as_int(training.get("attritions_observees")),
            "mois_min": _as_int(training.get("mois_min")) or None,
            "mois_max": _as_int(training.get("mois_max")) or None,
        },
        "model": {
            "exists": model_exists(),
            "model_code": metadata.get("model_code"),
            "trained_at": metadata.get("trained_at"),
            "training_rows": metadata.get("training_rows"),
            "positive_rows_total": metadata.get("positive_rows_total"),
            "validation_auc": metadata.get("validation_auc"),
            "validation_precision": metadata.get("validation_precision"),
            "validation_recall": metadata.get("validation_recall"),
        },
    }
