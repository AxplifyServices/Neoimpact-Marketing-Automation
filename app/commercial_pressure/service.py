from __future__ import annotations

from typing import Any, Dict

from app.storage.cibles_store_sqlite import build_db_cible_radicals_query
from app.storage.postgres_db import connection

WARNING_THRESHOLD_PCT = 25.0


def _rows_to_summary(rows: list[dict[str, Any]]) -> Dict[str, Any]:
    total = sum(int(row.get("clients") or 0) for row in rows)
    distribution = [
        {
            "niveau": str(row.get("niveau") or "non_score"),
            "clients": int(row.get("clients") or 0),
            "pct": (int(row.get("clients") or 0) / total * 100.0) if total else 0.0,
        }
        for row in rows
    ]
    elevated = next((item["clients"] for item in distribution if item["niveau"] == "Eleve"), 0)
    pct_eleve = (elevated / total * 100.0) if total else 0.0
    return {
        "supported": True,
        "total": total,
        "eleve": int(elevated),
        "pct_eleve": pct_eleve,
        "warning_threshold_pct": WARNING_THRESHOLD_PCT,
        "warning": bool(total > 0 and pct_eleve > WARNING_THRESHOLD_PCT),
        "distribution": distribution,
    }


def pressure_summary_for_cible(id_cible: str, *, exclude_rupture_relation: bool = False) -> Dict[str, Any]:
    """Répartition dynamique du score courant d'une cible.

    Aucun snapshot n'est utilisé : dès qu'un batch met à jour clients, la
    prochaine lecture de la cible reflète automatiquement la nouvelle pression.
    Les erreurs SQL remontent volontairement à l'appelant : une campagne ne doit
    pas contourner le contrôle de pression si ce contrôle est indisponible.
    """
    built = build_db_cible_radicals_query(
        id_cible,
        exclude_rupture_relation=exclude_rupture_relation,
    )
    if built is None:
        return {
            "supported": False,
            "total": 0,
            "eleve": 0,
            "pct_eleve": 0.0,
            "warning_threshold_pct": WARNING_THRESHOLD_PCT,
            "warning": False,
            "distribution": [],
        }
    radical_query, radical_params = built
    with connection(dict_rows=True) as conn:
        query_sql = radical_query.as_string(conn) if hasattr(radical_query, "as_string") else str(radical_query)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(c."Pression_commerciale", 'non_score') AS niveau,
                       COUNT(*) AS clients
                FROM ({}) AS q
                JOIN clients c ON c.radical_compte = q."Radical_compte"
                GROUP BY COALESCE(c."Pression_commerciale", 'non_score')
                ORDER BY CASE COALESCE(c."Pression_commerciale", 'non_score')
                    WHEN 'Eleve' THEN 1
                    WHEN 'Modere' THEN 2
                    WHEN 'Faible' THEN 3
                    ELSE 4
                END
                """.format(query_sql),
                radical_params,
            )
            rows = [dict(row) for row in cur.fetchall()]
    return _rows_to_summary(rows)


def pressure_summary_for_campaign(id_campagne: str) -> Dict[str, Any]:
    """Répartition de la population réellement attribuée à une campagne.

    Si la population n'est pas encore matérialisée, on retombe sur la cible
    avec les mêmes exclusions métier que la préparation de campagne.
    """
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id_cible
                FROM campagnes
                WHERE id_campagne = %s
                LIMIT 1
                """,
                (id_campagne,),
            )
            campaign = dict(cur.fetchone() or {})
            if not campaign:
                return {
                    "supported": False,
                    "total": 0,
                    "eleve": 0,
                    "pct_eleve": 0.0,
                    "warning_threshold_pct": WARNING_THRESHOLD_PCT,
                    "warning": False,
                    "distribution": [],
                }
            cur.execute(
                """
                SELECT COALESCE(c."Pression_commerciale", 'non_score') AS niveau,
                       COUNT(DISTINCT cc."Radical_compte") AS clients
                FROM clients_campagnes cc
                JOIN clients c ON c.radical_compte = cc."Radical_compte"
                WHERE cc."ID_CAMPAGNE" = %s
                GROUP BY COALESCE(c."Pression_commerciale", 'non_score')
                ORDER BY CASE COALESCE(c."Pression_commerciale", 'non_score')
                    WHEN 'Eleve' THEN 1
                    WHEN 'Modere' THEN 2
                    WHEN 'Faible' THEN 3
                    ELSE 4
                END
                """,
                (id_campagne,),
            )
            rows = [dict(row) for row in cur.fetchall()]
    summary = _rows_to_summary(rows)
    if summary["total"] > 0:
        return summary
    return pressure_summary_for_cible(
        str(campaign.get("id_cible") or ""),
        exclude_rupture_relation=True,
    )
