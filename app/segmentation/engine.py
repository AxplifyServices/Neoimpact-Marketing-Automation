from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from app.storage.postgres_db import get_connection

logger = logging.getLogger(__name__)

TIMEZONE = "Africa/Casablanca"
SEGMENTATION_ADVISORY_LOCK_KEY = 2_026_082_101


class SegmentationAlreadyRunningError(RuntimeError):
    """Une autre exécution de segmentation possède déjà le verrou global."""


class SegmentationDataNotReadyError(RuntimeError):
    """Le datamart mensuel n'est pas prêt pour la période demandée."""


@dataclass(frozen=True)
class PeriodReadiness:
    annee_mois: int
    client_count: int
    variable_count: int

    @property
    def ready(self) -> bool:
        return self.client_count > 0 and self.client_count == self.variable_count


def current_yyyymm() -> int:
    now = datetime.now(ZoneInfo(TIMEZONE))
    return now.year * 100 + now.month


def parse_yyyymm(value: str | int) -> int:
    raw = str(value).strip()
    if len(raw) != 6 or not raw.isdigit():
        raise ValueError(f"annee_mois invalide : {value!r}. Format attendu : YYYYMM.")
    result = int(raw)
    month = result % 100
    if month < 1 or month > 12:
        raise ValueError(f"annee_mois invalide : {value!r}.")
    return result


def _check_period_readiness(conn, annee_mois: int) -> PeriodReadiness:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM clients")
        client_count = int((cur.fetchone() or [0])[0] or 0)
        cur.execute(
            "SELECT COUNT(*) FROM dm_segmentation_variables WHERE annee_mois = %s",
            (annee_mois,),
        )
        variable_count = int((cur.fetchone() or [0])[0] or 0)
    return PeriodReadiness(
        annee_mois=annee_mois,
        client_count=client_count,
        variable_count=variable_count,
    )


def _create_due_base(conn, *, annee_mois: int, run_date: date) -> int:
    """Matérialise uniquement les clients arrivés à échéance de segmentation."""
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS tmp_segmentation_due_base")
        cur.execute(
            """
            CREATE TEMP TABLE tmp_segmentation_due_base
            ON COMMIT DROP
            AS
            WITH last_segmentation AS (
                SELECT radical_compte, MAX(date_segmentation) AS last_segmentation_date
                FROM dm_segmentation_resultats
                GROUP BY radical_compte
            )
            SELECT
                v.radical_compte,
                v.annee_mois,
                v.anciennete_mois,
                c."Age" AS age,
                c."Region" AS region,
                c."BP" AS bp,
                CASE
                    WHEN c."Age" IS NULL THEN NULL
                    WHEN c."Age" <= 17 THEN '0-17'
                    WHEN c."Age" <= 24 THEN '18-24'
                    WHEN c."Age" <= 34 THEN '25-34'
                    WHEN c."Age" <= 49 THEN '35-49'
                    WHEN c."Age" <= 60 THEN '50-60'
                    ELSE '60+'
                END AS tranche_age,
                ls.last_segmentation_date
            FROM dm_segmentation_variables AS v
            JOIN clients AS c
              ON c.radical_compte = v.radical_compte
            LEFT JOIN last_segmentation AS ls
              ON ls.radical_compte = v.radical_compte
            WHERE v.annee_mois = %s
              AND v.anciennete_mois >= 3
              AND (
                    ls.last_segmentation_date IS NULL
                    OR ls.last_segmentation_date <= (%s::date - INTERVAL '3 months')::date
              )
            """,
            (annee_mois, run_date),
        )
        cur.execute(
            "CREATE INDEX ON tmp_segmentation_due_base (radical_compte)"
        )
        cur.execute(
            "CREATE INDEX ON tmp_segmentation_due_base (region, tranche_age)"
        )
        cur.execute("ANALYZE tmp_segmentation_due_base")
        cur.execute("SELECT COUNT(*) FROM tmp_segmentation_due_base")
        return int((cur.fetchone() or [0])[0] or 0)


def _cached_medians_cover_due_groups(conn, *, annee_mois: int) -> bool:
    """Vrai si chaque groupe requis possède déjà ses médianes pour le mois.

    Les lignes Banque privée n'ont pas besoin d'une médiane : le notebook applique
    l'override BP après la classification.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH due_groups AS (
                SELECT DISTINCT region, tranche_age
                FROM tmp_segmentation_due_base
                WHERE region IS NOT NULL
                  AND tranche_age IS NOT NULL
                  AND LOWER(BTRIM(COALESCE(bp, ''))) NOT IN ('oui','yes','1','true')
            ), cached AS (
                SELECT region, tranche_age
                FROM dm_segmentation_resultats
                WHERE annee_mois = %s
                  AND mediane_flux IS NOT NULL
                  AND mediane_avoirs IS NOT NULL
                GROUP BY region, tranche_age
            )
            SELECT COUNT(*)
            FROM due_groups AS d
            LEFT JOIN cached AS c
              ON c.region IS NOT DISTINCT FROM d.region
             AND c.tranche_age IS NOT DISTINCT FROM d.tranche_age
            WHERE c.region IS NULL
            """,
            (annee_mois,),
        )
        missing = int((cur.fetchone() or [0])[0] or 0)
    return missing == 0


def _create_current_features(conn, *, annee_mois: int, due_only: bool) -> int:
    """Porte le calcul du notebook sur PostgreSQL sans charger 7,5 M lignes en RAM.

    Formules reprises :
    - fenêtre salarié = min(12, ancienneté) avec minimum 3 mois ;
    - fréquence des mois avec flux >= 2 000, seuil 80 % ;
    - moyenne/écart-type tronqués aux quantiles 10 %-90 % ;
    - salarié si fréquence >= 0,8 ET std/mean < 0,5 ;
    - lissage 3 mois des flux et des avoirs ;
    - avoir salarié = quantile bas lissé, sinon encours moyen lissé.
    """
    scope_join = (
        "JOIN tmp_segmentation_due_base AS scope ON scope.radical_compte = v.radical_compte"
        if due_only
        else ""
    )

    query = f"""
        CREATE TEMP TABLE tmp_segmentation_current
        ON COMMIT DROP
        AS
        WITH current_rows AS (
            SELECT
                v.radical_compte,
                v.annee_mois,
                v.anciennete_mois,
                c."Age" AS age,
                c."Region" AS region,
                c."BP" AS bp,
                CASE
                    WHEN c."Age" IS NULL THEN NULL
                    WHEN c."Age" <= 17 THEN '0-17'
                    WHEN c."Age" <= 24 THEN '18-24'
                    WHEN c."Age" <= 34 THEN '25-34'
                    WHEN c."Age" <= 49 THEN '35-49'
                    WHEN c."Age" <= 60 THEN '50-60'
                    ELSE '60+'
                END AS tranche_age,
                CASE
                    WHEN v.anciennete_mois >= 12 THEN 12
                    WHEN v.anciennete_mois >= 3 THEN v.anciennete_mois
                    ELSE NULL
                END AS evaluation_window
            FROM dm_segmentation_variables AS v
            JOIN clients AS c
              ON c.radical_compte = v.radical_compte
            {scope_join}
            WHERE v.annee_mois = %s
        ), history_ranked AS (
            SELECT
                cr.radical_compte,
                cr.annee_mois AS current_month,
                cr.anciennete_mois,
                cr.age,
                cr.region,
                cr.bp,
                cr.tranche_age,
                cr.evaluation_window,
                h.annee_mois,
                h.flux_crediteur_m,
                h.moyenne_10pc_plus_petits,
                h.encours_m_moyen,
                ROW_NUMBER() OVER (
                    PARTITION BY cr.radical_compte
                    ORDER BY h.annee_mois DESC
                ) AS rn
            FROM current_rows AS cr
            JOIN dm_segmentation_variables AS h
              ON h.radical_compte = cr.radical_compte
             AND h.annee_mois <= cr.annee_mois
        ), windowed AS (
            SELECT *
            FROM history_ranked
            WHERE evaluation_window IS NOT NULL
              AND rn <= evaluation_window
        ), quantiles AS (
            SELECT
                radical_compte,
                percentile_cont(0.10) WITHIN GROUP (ORDER BY flux_crediteur_m)::DOUBLE PRECISION AS q10_flux,
                percentile_cont(0.90) WITHIN GROUP (ORDER BY flux_crediteur_m)::DOUBLE PRECISION AS q90_flux
            FROM windowed
            GROUP BY radical_compte
        ), aggregated AS (
            SELECT
                w.radical_compte,
                MAX(w.evaluation_window) AS evaluation_window,
                (
                    COUNT(*) FILTER (WHERE w.flux_crediteur_m >= 2000)::DOUBLE PRECISION
                    / NULLIF(MAX(w.evaluation_window), 0)::DOUBLE PRECISION
                ) AS freq_prop,
                AVG(w.flux_crediteur_m) FILTER (
                    WHERE w.flux_crediteur_m >= q.q10_flux
                      AND w.flux_crediteur_m <= q.q90_flux
                )::DOUBLE PRECISION AS mean_trim_10_90,
                COALESCE(
                    STDDEV_SAMP(w.flux_crediteur_m) FILTER (
                        WHERE w.flux_crediteur_m >= q.q10_flux
                          AND w.flux_crediteur_m <= q.q90_flux
                    ),
                    0.0
                )::DOUBLE PRECISION AS std_trim_10_90,
                AVG(w.flux_crediteur_m) FILTER (WHERE w.rn <= 3)::DOUBLE PRECISION AS flux_crediteur_moy_3m,
                AVG(w.moyenne_10pc_plus_petits) FILTER (WHERE w.rn <= 3)::DOUBLE PRECISION AS moyenne_10pc_plus_petit_3m,
                AVG(w.encours_m_moyen) FILTER (WHERE w.rn <= 3)::DOUBLE PRECISION AS encours_m_moyen_3m
            FROM windowed AS w
            JOIN quantiles AS q
              ON q.radical_compte = w.radical_compte
            GROUP BY w.radical_compte
        )
        SELECT
            cr.radical_compte,
            cr.annee_mois,
            cr.age,
            cr.tranche_age,
            cr.region,
            cr.bp,
            cr.anciennete_mois,
            a.freq_prop,
            COALESCE(a.freq_prop >= 0.80, FALSE) AS meets_freq,
            a.mean_trim_10_90,
            a.std_trim_10_90,
            CASE
                WHEN a.mean_trim_10_90 > 0
                    THEN a.std_trim_10_90 / a.mean_trim_10_90
                WHEN cr.anciennete_mois >= 3
                    THEN 'Infinity'::DOUBLE PRECISION
                ELSE NULL
            END AS ratio_std_over_mean,
            COALESCE(
                a.mean_trim_10_90 > 0
                AND (a.std_trim_10_90 / a.mean_trim_10_90) < 0.5,
                FALSE
            ) AS meets_regularity,
            CASE
                WHEN cr.anciennete_mois < 3 THEN 'Non évalué (<3 mois)'
                WHEN COALESCE(a.freq_prop >= 0.80, FALSE)
                 AND COALESCE(
                    a.mean_trim_10_90 > 0
                    AND (a.std_trim_10_90 / a.mean_trim_10_90) < 0.5,
                    FALSE
                 ) THEN 'Salarié'
                ELSE 'Non Salarié'
            END AS statut_salarie,
            a.flux_crediteur_moy_3m,
            a.moyenne_10pc_plus_petit_3m,
            a.encours_m_moyen_3m,
            CASE
                WHEN COALESCE(a.freq_prop >= 0.80, FALSE)
                 AND COALESCE(
                    a.mean_trim_10_90 > 0
                    AND (a.std_trim_10_90 / a.mean_trim_10_90) < 0.5,
                    FALSE
                 )
                    THEN a.moyenne_10pc_plus_petit_3m
                ELSE a.encours_m_moyen_3m
            END AS encours_selon_statut
        FROM current_rows AS cr
        LEFT JOIN aggregated AS a
          ON a.radical_compte = cr.radical_compte;
    """

    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS tmp_segmentation_current")
        cur.execute(query, (annee_mois,))
        cur.execute("CREATE INDEX ON tmp_segmentation_current (radical_compte)")
        cur.execute("CREATE INDEX ON tmp_segmentation_current (region, tranche_age)")
        cur.execute("ANALYZE tmp_segmentation_current")
        cur.execute("SELECT COUNT(*) FROM tmp_segmentation_current")
        return int((cur.fetchone() or [0])[0] or 0)


def _create_medians_from_current(conn) -> int:
    """Calcule les médianes Région × tranche d'âge sur la population de référence."""
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS tmp_segmentation_medians")
        cur.execute(
            """
            CREATE TEMP TABLE tmp_segmentation_medians
            ON COMMIT DROP
            AS
            SELECT
                region,
                tranche_age,
                percentile_cont(0.50) WITHIN GROUP (
                    ORDER BY flux_crediteur_moy_3m
                )::DOUBLE PRECISION AS mediane_flux,
                percentile_cont(0.50) WITHIN GROUP (
                    ORDER BY encours_selon_statut
                )::DOUBLE PRECISION AS mediane_avoirs
            FROM tmp_segmentation_current
            WHERE anciennete_mois >= 3
              AND region IS NOT NULL
              AND tranche_age IS NOT NULL
              AND (
                    tranche_age = '0-17'
                    OR (
                        flux_crediteur_moy_3m >= 1000
                        AND encours_selon_statut >= 1000
                    )
              )
            GROUP BY region, tranche_age
            """
        )
        cur.execute("CREATE UNIQUE INDEX ON tmp_segmentation_medians (region, tranche_age)")
        cur.execute("ANALYZE tmp_segmentation_medians")
        cur.execute("SELECT COUNT(*) FROM tmp_segmentation_medians")
        return int((cur.fetchone() or [0])[0] or 0)


def _create_medians_from_history(conn, *, annee_mois: int) -> int:
    """Réutilise les médianes déjà archivées pendant le même mois."""
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS tmp_segmentation_medians")
        cur.execute(
            """
            CREATE TEMP TABLE tmp_segmentation_medians
            ON COMMIT DROP
            AS
            SELECT
                region,
                tranche_age,
                MAX(mediane_flux)::DOUBLE PRECISION AS mediane_flux,
                MAX(mediane_avoirs)::DOUBLE PRECISION AS mediane_avoirs
            FROM dm_segmentation_resultats
            WHERE annee_mois = %s
              AND region IS NOT NULL
              AND tranche_age IS NOT NULL
              AND mediane_flux IS NOT NULL
              AND mediane_avoirs IS NOT NULL
            GROUP BY region, tranche_age
            """,
            (annee_mois,),
        )
        cur.execute("CREATE UNIQUE INDEX ON tmp_segmentation_medians (region, tranche_age)")
        cur.execute("ANALYZE tmp_segmentation_medians")
        cur.execute("SELECT COUNT(*) FROM tmp_segmentation_medians")
        return int((cur.fetchone() or [0])[0] or 0)


def _create_due_results(conn, *, annee_mois: int) -> Dict[str, int]:
    """Applique les règles de segmentation du notebook aux clients dus."""
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS tmp_segmentation_due_results")
        cur.execute(
            """
            CREATE TEMP TABLE tmp_segmentation_due_results
            ON COMMIT DROP
            AS
            SELECT
                f.*,
                m.mediane_flux,
                m.mediane_avoirs,
                CASE
                    -- Override Banque privée du notebook.
                    WHEN LOWER(BTRIM(COALESCE(f.bp, ''))) IN ('oui','yes','1','true')
                        THEN 'Banque privée'

                    WHEN f.region IS NULL
                      OR f.tranche_age IS NULL
                      OR m.mediane_flux IS NULL
                      OR m.mediane_avoirs IS NULL
                        THEN 'Non segmenté'

                    -- Le notebook retourne le segment 1 si l'une des valeurs
                    -- calculées n'est pas disponible.
                    WHEN f.flux_crediteur_moy_3m IS NULL
                      OR f.encours_selon_statut IS NULL
                        THEN 'Mass Market'

                    -- Segment 4 : >= 10x sur au moins un critère.
                    WHEN f.flux_crediteur_moy_3m >= m.mediane_flux * 10
                      OR f.encours_selon_statut >= m.mediane_avoirs * 10
                        THEN 'Premium'

                    -- Segment 4 : >= 5x sur les deux critères.
                    WHEN f.flux_crediteur_moy_3m >= m.mediane_flux * 5
                     AND f.encours_selon_statut >= m.mediane_avoirs * 5
                        THEN 'Premium'

                    -- Le notebook Python fourni utilise bien 4x ici
                    -- (même si une présentation métier mentionne 5x).
                    WHEN (
                            f.flux_crediteur_moy_3m >= m.mediane_flux * 2
                        AND f.encours_selon_statut >= m.mediane_avoirs * 2
                    ) OR (
                            f.flux_crediteur_moy_3m >= m.mediane_flux * 4
                         OR f.encours_selon_statut >= m.mediane_avoirs * 4
                    )
                        THEN 'Haut de gamme'

                    WHEN f.flux_crediteur_moy_3m < m.mediane_flux
                     AND f.encours_selon_statut < m.mediane_avoirs
                        THEN 'Mass Market'

                    ELSE 'Medium'
                END AS segment
            FROM tmp_segmentation_current AS f
            JOIN tmp_segmentation_due_base AS d
              ON d.radical_compte = f.radical_compte
            LEFT JOIN tmp_segmentation_medians AS m
              ON m.region IS NOT DISTINCT FROM f.region
             AND m.tranche_age IS NOT DISTINCT FROM f.tranche_age
            WHERE f.annee_mois = %s
            """,
            (annee_mois,),
        )
        cur.execute("CREATE UNIQUE INDEX ON tmp_segmentation_due_results (radical_compte)")
        cur.execute("ANALYZE tmp_segmentation_due_results")
        cur.execute(
            """
            SELECT segment, COUNT(*)
            FROM tmp_segmentation_due_results
            GROUP BY segment
            ORDER BY segment
            """
        )
        return {str(segment): int(count) for segment, count in cur.fetchall()}


def _persist_results(conn, *, annee_mois: int, run_date: date, dry_run: bool) -> Dict[str, int]:
    if dry_run:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM tmp_segmentation_due_results")
            would_insert = int((cur.fetchone() or [0])[0] or 0)
        return {
            "inserted_results": 0,
            "updated_clients": 0,
            "cleared_unsegmented_clients": 0,
            "would_insert_results": would_insert,
        }

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dm_segmentation_resultats (
                radical_compte,
                annee_mois,
                date_segmentation,
                age,
                tranche_age,
                region,
                bp,
                anciennete_mois,
                freq_prop,
                meets_freq,
                mean_trim_10_90,
                std_trim_10_90,
                ratio_std_over_mean,
                meets_regularity,
                statut_salarie,
                flux_crediteur_moy_3m,
                moyenne_10pc_plus_petit_3m,
                encours_m_moyen_3m,
                encours_selon_statut,
                mediane_flux,
                mediane_avoirs,
                segment
            )
            SELECT
                radical_compte,
                annee_mois,
                %s::date,
                age,
                tranche_age,
                region,
                bp,
                anciennete_mois,
                freq_prop,
                meets_freq,
                mean_trim_10_90,
                std_trim_10_90,
                ratio_std_over_mean,
                meets_regularity,
                statut_salarie,
                flux_crediteur_moy_3m,
                moyenne_10pc_plus_petit_3m,
                encours_m_moyen_3m,
                encours_selon_statut,
                mediane_flux,
                mediane_avoirs,
                segment
            FROM tmp_segmentation_due_results
            ON CONFLICT (radical_compte, annee_mois) DO NOTHING
            """,
            (run_date,),
        )
        inserted = max(0, int(cur.rowcount or 0))

        # Segment_actuel reste toujours la dernière version réellement produite.
        # Pour un résultat technique "Non segmenté", la valeur courante est NULL.
        cur.execute(
            """
            UPDATE clients AS c
            SET "Segment_actuel" = CASE
                    WHEN r.segment = 'Non segmenté' THEN NULL
                    ELSE r.segment
                END
            FROM tmp_segmentation_due_results AS r
            WHERE c.radical_compte = r.radical_compte
              AND c."Segment_actuel" IS DISTINCT FROM CASE
                    WHEN r.segment = 'Non segmenté' THEN NULL
                    ELSE r.segment
                  END
            """
        )
        updated_clients = max(0, int(cur.rowcount or 0))

        # Un client de moins de 3 mois n'est pas segmenté. On retire donc une
        # éventuelle ancienne valeur fake de Segment_actuel tant qu'aucun vrai
        # résultat de segmentation n'existe pour lui.
        cur.execute(
            """
            UPDATE clients AS c
            SET "Segment_actuel" = NULL
            FROM dm_segmentation_variables AS v
            WHERE v.radical_compte = c.radical_compte
              AND v.annee_mois = %s
              AND v.anciennete_mois < 3
              AND c."Segment_actuel" IS NOT NULL
              AND NOT EXISTS (
                    SELECT 1
                    FROM dm_segmentation_resultats AS h
                    WHERE h.radical_compte = c.radical_compte
              )
            """
        ,
            (annee_mois,),
        )
        cleared = max(0, int(cur.rowcount or 0))

    return {
        "inserted_results": inserted,
        "updated_clients": updated_clients,
        "cleared_unsegmented_clients": cleared,
        "would_insert_results": 0,
    }


def run_segmentation_cycle(
    *,
    annee_mois: Optional[int] = None,
    run_date: Optional[date] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    target_month = parse_yyyymm(annee_mois or current_yyyymm())
    effective_date = run_date or datetime.now(ZoneInfo(TIMEZONE)).date()

    conn = get_connection(autocommit=False)
    lock_acquired = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_try_advisory_lock(%s)",
                (SEGMENTATION_ADVISORY_LOCK_KEY,),
            )
            row = cur.fetchone()
            lock_acquired = bool(row and row[0])
        if not lock_acquired:
            raise SegmentationAlreadyRunningError(
                "Une autre exécution de segmentation est déjà en cours."
            )

        readiness = _check_period_readiness(conn, target_month)
        if not readiness.ready:
            raise SegmentationDataNotReadyError(
                "Datamart segmentation incomplet pour "
                f"{target_month}: clients={readiness.client_count:,}, "
                f"lignes_mois={readiness.variable_count:,}. "
                "Le scoring est volontairement bloqué pour éviter un résultat partiel."
            )

        due_count = _create_due_base(
            conn,
            annee_mois=target_month,
            run_date=effective_date,
        )
        if due_count == 0:
            if dry_run:
                conn.rollback()
            else:
                conn.commit()
            return {
                "ok": True,
                "dry_run": dry_run,
                "annee_mois": target_month,
                "run_date": effective_date.isoformat(),
                "clients": readiness.client_count,
                "due_clients": 0,
                "feature_scope": "none",
                "reference_groups": 0,
                "segments": {},
                "inserted_results": 0,
                "updated_clients": 0,
                "cleared_unsegmented_clients": 0,
            }

        cached = _cached_medians_cover_due_groups(conn, annee_mois=target_month)
        # Première exécution d'un mois : on calcule les médianes sur toute la
        # population. Les jours suivants, on réutilise les médianes archivées et
        # on ne recalcule les features que pour les clients arrivés à échéance.
        due_only = cached
        feature_rows = _create_current_features(
            conn,
            annee_mois=target_month,
            due_only=due_only,
        )
        if cached:
            median_groups = _create_medians_from_history(conn, annee_mois=target_month)
            feature_scope = "due_clients"
        else:
            median_groups = _create_medians_from_current(conn)
            feature_scope = "full_reference_population"

        distribution = _create_due_results(conn, annee_mois=target_month)
        persisted = _persist_results(
            conn,
            annee_mois=target_month,
            run_date=effective_date,
            dry_run=dry_run,
        )

        result: Dict[str, Any] = {
            "ok": True,
            "dry_run": dry_run,
            "annee_mois": target_month,
            "run_date": effective_date.isoformat(),
            "clients": readiness.client_count,
            "due_clients": due_count,
            "feature_rows": feature_rows,
            "feature_scope": feature_scope,
            "reference_groups": median_groups,
            "segments": distribution,
            **persisted,
        }

        if dry_run:
            conn.rollback()
        else:
            conn.commit()
        return result

    except Exception:
        conn.rollback()
        raise
    finally:
        if lock_acquired:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT pg_advisory_unlock(%s)",
                        (SEGMENTATION_ADVISORY_LOCK_KEY,),
                    )
                conn.commit()
            except Exception:
                logger.exception("Impossible de libérer le verrou de segmentation.")
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Moteur de segmentation client MVP.")
    parser.add_argument(
        "--month",
        default=str(current_yyyymm()),
        help="Période de calcul YYYYMM (défaut : mois courant).",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Date métier YYYY-MM-DD (défaut : aujourd'hui Africa/Casablanca).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calcule tout mais n'écrit ni l'historique ni Segment_actuel.",
    )
    args = parser.parse_args()

    parsed_date = date.fromisoformat(args.date) if args.date else None
    result = run_segmentation_cycle(
        annee_mois=parse_yyyymm(args.month),
        run_date=parsed_date,
        dry_run=bool(args.dry_run),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
