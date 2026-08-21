from __future__ import annotations

import argparse
import json
import logging
from datetime import date
from typing import Any, Dict

from app.digital_engagement.datamart import current_annee_mois, ensure_month_data
from app.storage.postgres_db import connection

logger = logging.getLogger(__name__)

DIGITAL_ENGAGEMENT_ADVISORY_LOCK = 882_821_2026


class DigitalEngagementAlreadyRunningError(RuntimeError):
    pass


def _current_month_complete(conn, *, annee_mois: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM clients AS c
            WHERE LOWER(BTRIM(COALESCE(c."STATUT_CLIENT", ''))) IN (LOWER('Actif'), LOWER('Inactif'))
              AND NOT EXISTS (
                    SELECT 1
                    FROM dm_engagement_digital_resultats AS r
                    WHERE r.radical_compte = c.radical_compte
                      AND r.annee_mois = %s
              )
            """,
            (annee_mois,),
        )
        missing = int((cur.fetchone() or [0])[0] or 0)

        cur.execute(
            """
            SELECT COUNT(*)
            FROM clients
            WHERE LOWER(BTRIM(COALESCE("STATUT_CLIENT", ''))) NOT IN (LOWER('Actif'), LOWER('Inactif'))
              AND (
                    "Engagement_digital" <> 'non_score'
                    OR "Creneau_connexion" <> 'non_score'
              )
            """
        )
        stale = int((cur.fetchone() or [0])[0] or 0)
    return missing == 0 and stale == 0


def _resolve_median(conn, *, annee_mois: int) -> float:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY v.moyenne_connexions_jour)
            FROM dm_engagement_digital_variables AS v
            JOIN clients AS c ON c.radical_compte = v.radical_compte
            WHERE v.annee_mois = %s
              AND LOWER(BTRIM(COALESCE(c."STATUT_CLIENT", ''))) IN (LOWER('Actif'), LOWER('Inactif'))
            """,
            (annee_mois,),
        )
        median = float((cur.fetchone() or [0.0])[0] or 0.0)

        # Sécurité pour une population majoritairement sans connexion.
        if median <= 0:
            cur.execute(
                """
                SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY v.moyenne_connexions_jour)
                FROM dm_engagement_digital_variables AS v
                JOIN clients AS c ON c.radical_compte = v.radical_compte
                WHERE v.annee_mois = %s
                  AND v.moyenne_connexions_jour > 0
                  AND LOWER(BTRIM(COALESCE(c."STATUT_CLIENT", ''))) IN (LOWER('Actif'), LOWER('Inactif'))
                """,
                (annee_mois,),
            )
            median = float((cur.fetchone() or [0.0])[0] or 0.0)
    return max(0.0, median)


def _compute_scores(conn, *, annee_mois: int, run_date: date, median: float) -> Dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dm_engagement_digital_resultats (
                radical_compte,
                annee_mois,
                date_calcul,
                statut_client_snapshot,
                region,
                nb_connexions_mois,
                moyenne_connexions_jour,
                mediane_connexions_jour,
                engagement_digital,
                heure_moyenne_ponderee,
                creneau_connexion,
                created_at
            )
            SELECT
                v.radical_compte,
                v.annee_mois,
                %s,
                v.statut_client_snapshot,
                v.region,
                v.nb_connexions_mois,
                v.moyenne_connexions_jour,
                %s,
                CASE
                    WHEN v.moyenne_connexions_jour < %s THEN 'Faible'
                    WHEN v.moyenne_connexions_jour > (2.0 * %s) THEN 'Eleve'
                    ELSE 'Modere'
                END,
                v.heure_moyenne_ponderee,
                CASE
                    WHEN v.nb_connexions_mois <= 0 OR v.heure_moyenne_ponderee IS NULL THEN 'non_score'
                    WHEN v.heure_moyenne_ponderee >= 5 AND v.heure_moyenne_ponderee < 12 THEN 'Matin'
                    WHEN v.heure_moyenne_ponderee >= 12 AND v.heure_moyenne_ponderee < 18 THEN 'Apres-midi'
                    ELSE 'Soir'
                END,
                NOW()
            FROM dm_engagement_digital_variables AS v
            JOIN clients AS c ON c.radical_compte = v.radical_compte
            WHERE v.annee_mois = %s
              AND LOWER(BTRIM(COALESCE(c."STATUT_CLIENT", ''))) IN (LOWER('Actif'), LOWER('Inactif'))
            ON CONFLICT (radical_compte, annee_mois) DO UPDATE SET
                date_calcul = EXCLUDED.date_calcul,
                statut_client_snapshot = EXCLUDED.statut_client_snapshot,
                region = EXCLUDED.region,
                nb_connexions_mois = EXCLUDED.nb_connexions_mois,
                moyenne_connexions_jour = EXCLUDED.moyenne_connexions_jour,
                mediane_connexions_jour = EXCLUDED.mediane_connexions_jour,
                engagement_digital = EXCLUDED.engagement_digital,
                heure_moyenne_ponderee = EXCLUDED.heure_moyenne_ponderee,
                creneau_connexion = EXCLUDED.creneau_connexion,
                created_at = NOW()
            """,
            (run_date, median, median, median, annee_mois),
        )
        result_rows = int(cur.rowcount or 0)

        cur.execute(
            """
            UPDATE clients AS c
            SET
                "Engagement_digital" = r.engagement_digital,
                "Creneau_connexion" = r.creneau_connexion
            FROM dm_engagement_digital_resultats AS r
            WHERE r.radical_compte = c.radical_compte
              AND r.annee_mois = %s
              AND (
                    c."Engagement_digital" IS DISTINCT FROM r.engagement_digital
                    OR c."Creneau_connexion" IS DISTINCT FROM r.creneau_connexion
              )
            """,
            (annee_mois,),
        )
        updated_clients = int(cur.rowcount or 0)

        cur.execute(
            """
            UPDATE clients
            SET
                "Engagement_digital" = 'non_score',
                "Creneau_connexion" = 'non_score'
            WHERE LOWER(BTRIM(COALESCE("STATUT_CLIENT", ''))) NOT IN (LOWER('Actif'), LOWER('Inactif'))
              AND (
                    "Engagement_digital" IS DISTINCT FROM 'non_score'
                    OR "Creneau_connexion" IS DISTINCT FROM 'non_score'
              )
            """
        )
        cleared_non_scored = int(cur.rowcount or 0)

        cur.execute(
            """
            SELECT engagement_digital, COUNT(*)
            FROM dm_engagement_digital_resultats
            WHERE annee_mois = %s
            GROUP BY engagement_digital
            ORDER BY engagement_digital
            """,
            (annee_mois,),
        )
        engagement = {str(row[0]): int(row[1]) for row in cur.fetchall()}

        cur.execute(
            """
            SELECT creneau_connexion, COUNT(*)
            FROM dm_engagement_digital_resultats
            WHERE annee_mois = %s
            GROUP BY creneau_connexion
            ORDER BY creneau_connexion
            """,
            (annee_mois,),
        )
        slots = {str(row[0]): int(row[1]) for row in cur.fetchall()}

    return {
        "result_rows": result_rows,
        "updated_clients": updated_clients,
        "cleared_non_scored": cleared_non_scored,
        "engagement": engagement,
        "creneaux": slots,
    }


def run_digital_engagement_cycle(
    *,
    annee_mois: int | None = None,
    run_date: date | None = None,
    force: bool = False,
) -> Dict[str, Any]:
    month = int(annee_mois or current_annee_mois(run_date))
    today = run_date or date.today()
    datamart = ensure_month_data(annee_mois=month)

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_xact_lock(%s)", (DIGITAL_ENGAGEMENT_ADVISORY_LOCK,))
            locked = bool((cur.fetchone() or [False])[0])
            if not locked:
                raise DigitalEngagementAlreadyRunningError(
                    "Un calcul engagement digital est déjà en cours."
                )

        if not force and _current_month_complete(conn, annee_mois=month):
            return {
                "ok": True,
                "skipped": True,
                "reason": "already_scored_current_month",
                "annee_mois": month,
                "run_date": str(today),
                "datamart": datamart,
            }

        median = _resolve_median(conn, annee_mois=month)
        scoring = _compute_scores(
            conn,
            annee_mois=month,
            run_date=today,
            median=median,
        )

    return {
        "ok": True,
        "skipped": False,
        "annee_mois": month,
        "run_date": str(today),
        "mediane_connexions_jour": median,
        "threshold_high": median * 2.0,
        "datamart": datamart,
        **scoring,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Moteur mensuel d'engagement digital")
    parser.add_argument("--month", type=int, dest="annee_mois")
    parser.add_argument("--date", dest="run_date")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    run_date = date.fromisoformat(args.run_date) if args.run_date else None
    result = run_digital_engagement_cycle(
        annee_mois=args.annee_mois,
        run_date=run_date,
        force=bool(args.force),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
