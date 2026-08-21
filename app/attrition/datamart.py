from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Iterable, Tuple

from app.storage.postgres_db import connection

logger = logging.getLogger(__name__)


def _month_to_date(annee_mois: int) -> date:
    year = int(annee_mois) // 100
    month = int(annee_mois) % 100
    if month < 1 or month > 12:
        raise ValueError(f"annee_mois invalide: {annee_mois}")
    return date(year, month, 1)


def shift_month(annee_mois: int, delta: int) -> int:
    base = _month_to_date(annee_mois)
    index = base.year * 12 + (base.month - 1) + int(delta)
    year, month0 = divmod(index, 12)
    return year * 100 + month0 + 1


def current_annee_mois(today: date | None = None) -> int:
    current = today or date.today()
    return current.year * 100 + current.month


def _pct_change_sql(current_expr: str, ref_expr: str) -> str:
    # Les montants sont non négatifs. Une baisse de 20 % donne -0.2,
    # une hausse de 20 % donne +0.2. Le plancher 1 MAD évite les divisions
    # impossibles sur des comptes très proches de zéro.
    return (
        f"CASE WHEN {ref_expr} IS NULL THEN 0.0 "
        f"ELSE GREATEST(-1.0, LEAST(5.0, (({current_expr}) - ({ref_expr})) / "
        f"GREATEST(ABS({ref_expr}), 1.0))) END"
    )


def ensure_fake_history_if_empty(*, annee_mois: int | None = None) -> Dict[str, Any]:
    """Bootstrap de l'historique d'attrition pour le MVP.

    Le système ne crée aucun client. Il enrichit les clients existants en
    construisant jusqu'à 12 mois de trajectoire à partir de leurs trois signaux
    financiers actuels. Les clients déjà en rupture ont une profondeur variable
    de 3 à 12 mois et leur dernière ligne porte attrition=1.

    Cette fonction est idempotente: si le datamart contient déjà des lignes,
    elle ne régénère rien.
    """
    month = int(annee_mois or current_annee_mois())
    previous_month = shift_month(month, -1)

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM dm_attrition_variables")
            existing = int((cur.fetchone() or [0])[0] or 0)
            if existing > 0:
                return {
                    "ok": True,
                    "bootstrapped": False,
                    "rows": existing,
                    "end_month": previous_month,
                }

            logger.info("Bootstrap du datamart attrition à partir des clients existants...")

            # La série est volontairement synthétique: l'objectif du MVP est de
            # valider la chaîne de calcul / entraînement / scoring. Les trois
            # niveaux courants viennent bien de clients; seule leur profondeur
            # historique est simulée.
            cur.execute(
                """
                WITH base AS (
                    SELECT
                        c.radical_compte,
                        c."STATUT_CLIENT" AS statut_client,
                        GREATEST(COALESCE(c.solde_moyen_depots, 0), 0)::DOUBLE PRECISION AS current_avoirs,
                        GREATEST(COALESCE(c.montant_revenu, 0), 0)::DOUBLE PRECISION AS current_credit,
                        (
                            GREATEST(COALESCE(c.vol_transaction, 0), 0)
                          + GREATEST(COALESCE(c.vol_retrait_gab, 0), 0)
                          + GREATEST(COALESCE(c.vol_virement, 0), 0)
                        )::DOUBLE PRECISION AS current_debit,
                        CASE
                            WHEN LOWER(BTRIM(COALESCE(c."STATUT_CLIENT", ''))) = LOWER('Rupture de relation')
                                THEN 3 + MOD((hashtextextended(c.radical_compte, 11) & 2147483647), 10)::INTEGER
                            ELSE 12
                        END AS history_len,
                        CASE
                            WHEN LOWER(BTRIM(COALESCE(c."STATUT_CLIENT", ''))) = LOWER('Rupture de relation')
                                THEN MOD((hashtextextended(c.radical_compte, 17) & 2147483647), 6)::INTEGER
                            ELSE 0
                        END AS rupture_offset
                    FROM clients AS c
                    WHERE LOWER(BTRIM(COALESCE(c."STATUT_CLIENT", ''))) IN (
                        LOWER('Actif'), LOWER('Inactif'), LOWER('Rupture de relation')
                    )
                ), expanded AS (
                    SELECT
                        b.*,
                        gs.i,
                        (b.history_len - 1 - gs.i) AS reverse_i,
                        CASE WHEN b.history_len <= 1 THEN 1.0
                             ELSE gs.i::DOUBLE PRECISION / (b.history_len - 1)::DOUBLE PRECISION
                        END AS progress
                    FROM base AS b
                    CROSS JOIN LATERAL generate_series(0, b.history_len - 1) AS gs(i)
                ), raw AS (
                    SELECT
                        e.radical_compte,
                        (
                            EXTRACT(YEAR FROM m.month_date)::INTEGER * 100
                          + EXTRACT(MONTH FROM m.month_date)::INTEGER
                        ) AS annee_mois,
                        e.statut_client AS statut_client_snapshot,
                        CASE
                            WHEN LOWER(BTRIM(COALESCE(e.statut_client, ''))) = LOWER('Rupture de relation')
                                THEN GREATEST(0,
                                    (GREATEST(e.current_avoirs, 2500.0)
                                      * (1.0 + (1.0 - e.progress) * 2.6)
                                      * n.noise_avoirs)
                                )
                            WHEN LOWER(BTRIM(COALESCE(e.statut_client, ''))) = LOWER('Inactif')
                                THEN GREATEST(0, GREATEST(e.current_avoirs, 1500.0) * (1.0 + (1.0 - e.progress) * 0.35) * n.noise_avoirs)
                            ELSE GREATEST(0, GREATEST(e.current_avoirs, 1500.0) * n.noise_avoirs)
                        END::DOUBLE PRECISION AS avoirs,
                        CASE
                            WHEN LOWER(BTRIM(COALESCE(e.statut_client, ''))) = LOWER('Rupture de relation')
                                THEN GREATEST(0,
                                    (GREATEST(e.current_credit, 1800.0)
                                      * (1.0 + (1.0 - e.progress) * 2.2)
                                      * n.noise_credit)
                                )
                            WHEN LOWER(BTRIM(COALESCE(e.statut_client, ''))) = LOWER('Inactif')
                                THEN GREATEST(0, GREATEST(e.current_credit, 1200.0) * (1.0 + (1.0 - e.progress) * 0.25) * n.noise_credit)
                            ELSE GREATEST(0, GREATEST(e.current_credit, 1200.0) * n.noise_credit)
                        END::DOUBLE PRECISION AS flux_crediteurs,
                        CASE
                            WHEN LOWER(BTRIM(COALESCE(e.statut_client, ''))) = LOWER('Rupture de relation')
                                THEN GREATEST(0,
                                    (GREATEST(e.current_debit, 1600.0)
                                      * (1.0 + (1.0 - e.progress) * 1.8)
                                      * n.noise_debit)
                                )
                            WHEN LOWER(BTRIM(COALESCE(e.statut_client, ''))) = LOWER('Inactif')
                                THEN GREATEST(0, GREATEST(e.current_debit, 1000.0) * (1.0 + (1.0 - e.progress) * 0.20) * n.noise_debit)
                            ELSE GREATEST(0, GREATEST(e.current_debit, 1000.0) * n.noise_debit)
                        END::DOUBLE PRECISION AS flux_debiteurs,
                        CASE
                            WHEN LOWER(BTRIM(COALESCE(e.statut_client, ''))) = LOWER('Rupture de relation')
                             AND e.i = e.history_len - 1
                                THEN 1
                            ELSE 0
                        END::SMALLINT AS attrition
                    FROM expanded AS e
                    CROSS JOIN LATERAL (
                        SELECT (
                            make_date((%s / 100)::INTEGER, (%s %% 100)::INTEGER, 1)
                            - make_interval(months => (e.reverse_i + e.rupture_offset)::INTEGER)
                        )::DATE AS month_date
                    ) AS m
                    CROSS JOIN LATERAL (
                        SELECT
                            (0.92 + 0.16 * (((hashtextextended(e.radical_compte || ':' || m.month_date::TEXT || ':a', 101) & 2147483647) %% 10000)::DOUBLE PRECISION / 10000.0)) AS noise_avoirs,
                            (0.92 + 0.16 * (((hashtextextended(e.radical_compte || ':' || m.month_date::TEXT || ':c', 103) & 2147483647) %% 10000)::DOUBLE PRECISION / 10000.0)) AS noise_credit,
                            (0.92 + 0.16 * (((hashtextextended(e.radical_compte || ':' || m.month_date::TEXT || ':d', 107) & 2147483647) %% 10000)::DOUBLE PRECISION / 10000.0)) AS noise_debit
                    ) AS n
                ), with_lags AS (
                    SELECT
                        r.*,
                        LAG(r.avoirs, 1) OVER w AS a1,
                        AVG(r.avoirs) OVER (PARTITION BY r.radical_compte ORDER BY r.annee_mois ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS a3,
                        AVG(r.avoirs) OVER (PARTITION BY r.radical_compte ORDER BY r.annee_mois ROWS BETWEEN 6 PRECEDING AND 1 PRECEDING) AS a6,
                        AVG(r.avoirs) OVER (PARTITION BY r.radical_compte ORDER BY r.annee_mois ROWS BETWEEN 12 PRECEDING AND 1 PRECEDING) AS a12,
                        LAG(r.flux_crediteurs, 1) OVER w AS c1,
                        AVG(r.flux_crediteurs) OVER (PARTITION BY r.radical_compte ORDER BY r.annee_mois ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS c3,
                        AVG(r.flux_crediteurs) OVER (PARTITION BY r.radical_compte ORDER BY r.annee_mois ROWS BETWEEN 6 PRECEDING AND 1 PRECEDING) AS c6,
                        AVG(r.flux_crediteurs) OVER (PARTITION BY r.radical_compte ORDER BY r.annee_mois ROWS BETWEEN 12 PRECEDING AND 1 PRECEDING) AS c12,
                        LAG(r.flux_debiteurs, 1) OVER w AS d1,
                        AVG(r.flux_debiteurs) OVER (PARTITION BY r.radical_compte ORDER BY r.annee_mois ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS d3,
                        AVG(r.flux_debiteurs) OVER (PARTITION BY r.radical_compte ORDER BY r.annee_mois ROWS BETWEEN 6 PRECEDING AND 1 PRECEDING) AS d6,
                        AVG(r.flux_debiteurs) OVER (PARTITION BY r.radical_compte ORDER BY r.annee_mois ROWS BETWEEN 12 PRECEDING AND 1 PRECEDING) AS d12
                    FROM raw AS r
                    WINDOW w AS (PARTITION BY r.radical_compte ORDER BY r.annee_mois)
                )
                INSERT INTO dm_attrition_variables (
                    radical_compte, annee_mois, statut_client_snapshot,
                    avoirs, flux_crediteurs, flux_debiteurs,
                    var_avoirs_1m, var_avoirs_3m, var_avoirs_6m, var_avoirs_12m,
                    var_flux_crediteurs_1m, var_flux_crediteurs_3m, var_flux_crediteurs_6m, var_flux_crediteurs_12m,
                    var_flux_debiteurs_1m, var_flux_debiteurs_3m, var_flux_debiteurs_6m, var_flux_debiteurs_12m,
                    attrition
                )
                SELECT
                    radical_compte, annee_mois, statut_client_snapshot,
                    avoirs, flux_crediteurs, flux_debiteurs,
                    CASE WHEN a1 IS NULL THEN 0 ELSE GREATEST(-1.0, LEAST(5.0, (avoirs - a1) / GREATEST(ABS(a1), 1.0))) END,
                    CASE WHEN a3 IS NULL THEN 0 ELSE GREATEST(-1.0, LEAST(5.0, (avoirs - a3) / GREATEST(ABS(a3), 1.0))) END,
                    CASE WHEN a6 IS NULL THEN 0 ELSE GREATEST(-1.0, LEAST(5.0, (avoirs - a6) / GREATEST(ABS(a6), 1.0))) END,
                    CASE WHEN a12 IS NULL THEN 0 ELSE GREATEST(-1.0, LEAST(5.0, (avoirs - a12) / GREATEST(ABS(a12), 1.0))) END,
                    CASE WHEN c1 IS NULL THEN 0 ELSE GREATEST(-1.0, LEAST(5.0, (flux_crediteurs - c1) / GREATEST(ABS(c1), 1.0))) END,
                    CASE WHEN c3 IS NULL THEN 0 ELSE GREATEST(-1.0, LEAST(5.0, (flux_crediteurs - c3) / GREATEST(ABS(c3), 1.0))) END,
                    CASE WHEN c6 IS NULL THEN 0 ELSE GREATEST(-1.0, LEAST(5.0, (flux_crediteurs - c6) / GREATEST(ABS(c6), 1.0))) END,
                    CASE WHEN c12 IS NULL THEN 0 ELSE GREATEST(-1.0, LEAST(5.0, (flux_crediteurs - c12) / GREATEST(ABS(c12), 1.0))) END,
                    CASE WHEN d1 IS NULL THEN 0 ELSE GREATEST(-1.0, LEAST(5.0, (flux_debiteurs - d1) / GREATEST(ABS(d1), 1.0))) END,
                    CASE WHEN d3 IS NULL THEN 0 ELSE GREATEST(-1.0, LEAST(5.0, (flux_debiteurs - d3) / GREATEST(ABS(d3), 1.0))) END,
                    CASE WHEN d6 IS NULL THEN 0 ELSE GREATEST(-1.0, LEAST(5.0, (flux_debiteurs - d6) / GREATEST(ABS(d6), 1.0))) END,
                    CASE WHEN d12 IS NULL THEN 0 ELSE GREATEST(-1.0, LEAST(5.0, (flux_debiteurs - d12) / GREATEST(ABS(d12), 1.0))) END,
                    attrition
                FROM with_lags
                ON CONFLICT (radical_compte, annee_mois) DO NOTHING
                """,
                (previous_month, previous_month),
            )
            inserted = int(cur.rowcount or 0)

            cur.execute("SELECT COUNT(*) FROM dm_attrition_variables")
            total = int((cur.fetchone() or [0])[0] or 0)
            cur.execute("SELECT COUNT(*) FROM dm_attrition_variables WHERE attrition = 1")
            positives = int((cur.fetchone() or [0])[0] or 0)

    logger.info(
        "Bootstrap attrition terminé: rows=%s positives=%s end_month=%s",
        total,
        positives,
        previous_month,
    )
    return {
        "ok": True,
        "bootstrapped": True,
        "rows_inserted": inserted,
        "rows": total,
        "positives": positives,
        "end_month": previous_month,
    }


def _current_value_expressions(alias: str = "c") -> Tuple[str, str, str]:
    avoirs = f"GREATEST(COALESCE({alias}.solde_moyen_depots, 0), 0)::DOUBLE PRECISION"
    credits = f"GREATEST(COALESCE({alias}.montant_revenu, 0), 0)::DOUBLE PRECISION"
    debits = (
        f"(GREATEST(COALESCE({alias}.vol_transaction, 0), 0) + "
        f"GREATEST(COALESCE({alias}.vol_retrait_gab, 0), 0) + "
        f"GREATEST(COALESCE({alias}.vol_virement, 0), 0))::DOUBLE PRECISION"
    )
    return avoirs, credits, debits


def create_current_feature_table(conn, *, annee_mois: int, include_statuses: Iterable[str]) -> int:
    """Construit la ligne courante à scorer à partir de clients + historique.

    Les variations sont des pourcentages relatifs au mois précédent et aux
    moyennes des 3, 6 et 12 derniers mois disponibles, hors mois courant.
    """
    statuses = [str(value).strip() for value in include_statuses if str(value).strip()]
    if not statuses:
        raise ValueError("include_statuses ne peut pas être vide")

    avoirs, credits, debits = _current_value_expressions("c")
    status_placeholders = ", ".join(["%s"] * len(statuses))

    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS tmp_attrition_current_features")
        cur.execute(
            f"""
            CREATE TEMP TABLE tmp_attrition_current_features
            ON COMMIT DROP
            AS
            WITH current_values AS (
                SELECT
                    c.radical_compte,
                    c."STATUT_CLIENT" AS statut_client,
                    c."Region" AS region,
                    {avoirs} AS avoirs,
                    {credits} AS flux_crediteurs,
                    {debits} AS flux_debiteurs
                FROM clients AS c
                WHERE LOWER(BTRIM(COALESCE(c."STATUT_CLIENT", ''))) IN ({status_placeholders})
            ), history_ranked AS (
                SELECT
                    cv.radical_compte,
                    h.avoirs,
                    h.flux_crediteurs,
                    h.flux_debiteurs,
                    ROW_NUMBER() OVER (
                        PARTITION BY cv.radical_compte
                        ORDER BY h.annee_mois DESC
                    ) AS rn
                FROM current_values AS cv
                LEFT JOIN dm_attrition_variables AS h
                  ON h.radical_compte = cv.radical_compte
                 AND h.annee_mois < %s
            ), refs AS (
                SELECT
                    radical_compte,
                    AVG(avoirs) FILTER (WHERE rn <= 1) AS a1,
                    AVG(avoirs) FILTER (WHERE rn <= 3) AS a3,
                    AVG(avoirs) FILTER (WHERE rn <= 6) AS a6,
                    AVG(avoirs) FILTER (WHERE rn <= 12) AS a12,
                    AVG(flux_crediteurs) FILTER (WHERE rn <= 1) AS c1,
                    AVG(flux_crediteurs) FILTER (WHERE rn <= 3) AS c3,
                    AVG(flux_crediteurs) FILTER (WHERE rn <= 6) AS c6,
                    AVG(flux_crediteurs) FILTER (WHERE rn <= 12) AS c12,
                    AVG(flux_debiteurs) FILTER (WHERE rn <= 1) AS d1,
                    AVG(flux_debiteurs) FILTER (WHERE rn <= 3) AS d3,
                    AVG(flux_debiteurs) FILTER (WHERE rn <= 6) AS d6,
                    AVG(flux_debiteurs) FILTER (WHERE rn <= 12) AS d12
                FROM history_ranked
                WHERE rn <= 12
                GROUP BY radical_compte
            )
            SELECT
                cv.radical_compte,
                %s::INTEGER AS annee_mois,
                cv.statut_client,
                cv.region,
                cv.avoirs,
                cv.flux_crediteurs,
                cv.flux_debiteurs,
                {_pct_change_sql('cv.avoirs', 'r.a1')} AS var_avoirs_1m,
                {_pct_change_sql('cv.avoirs', 'r.a3')} AS var_avoirs_3m,
                {_pct_change_sql('cv.avoirs', 'r.a6')} AS var_avoirs_6m,
                {_pct_change_sql('cv.avoirs', 'r.a12')} AS var_avoirs_12m,
                {_pct_change_sql('cv.flux_crediteurs', 'r.c1')} AS var_flux_crediteurs_1m,
                {_pct_change_sql('cv.flux_crediteurs', 'r.c3')} AS var_flux_crediteurs_3m,
                {_pct_change_sql('cv.flux_crediteurs', 'r.c6')} AS var_flux_crediteurs_6m,
                {_pct_change_sql('cv.flux_crediteurs', 'r.c12')} AS var_flux_crediteurs_12m,
                {_pct_change_sql('cv.flux_debiteurs', 'r.d1')} AS var_flux_debiteurs_1m,
                {_pct_change_sql('cv.flux_debiteurs', 'r.d3')} AS var_flux_debiteurs_3m,
                {_pct_change_sql('cv.flux_debiteurs', 'r.d6')} AS var_flux_debiteurs_6m,
                {_pct_change_sql('cv.flux_debiteurs', 'r.d12')} AS var_flux_debiteurs_12m
            FROM current_values AS cv
            LEFT JOIN refs AS r USING (radical_compte)
            """,
            tuple([status.lower() for status in statuses]) + (annee_mois, annee_mois),
        )
        cur.execute("CREATE UNIQUE INDEX ON tmp_attrition_current_features (radical_compte)")
        cur.execute("ANALYZE tmp_attrition_current_features")
        cur.execute("SELECT COUNT(*) FROM tmp_attrition_current_features")
        return int((cur.fetchone() or [0])[0] or 0)

def materialize_new_ruptures(conn, *, annee_mois: int) -> int:
    """Archive les ruptures observées depuis le dernier batch avec cible=1."""
    create_current_feature_table(conn, annee_mois=annee_mois, include_statuses=["Rupture de relation"])
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dm_attrition_variables (
                radical_compte, annee_mois, statut_client_snapshot,
                avoirs, flux_crediteurs, flux_debiteurs,
                var_avoirs_1m, var_avoirs_3m, var_avoirs_6m, var_avoirs_12m,
                var_flux_crediteurs_1m, var_flux_crediteurs_3m, var_flux_crediteurs_6m, var_flux_crediteurs_12m,
                var_flux_debiteurs_1m, var_flux_debiteurs_3m, var_flux_debiteurs_6m, var_flux_debiteurs_12m,
                attrition, updated_at
            )
            SELECT
                f.radical_compte, f.annee_mois, f.statut_client,
                f.avoirs, f.flux_crediteurs, f.flux_debiteurs,
                f.var_avoirs_1m, f.var_avoirs_3m, f.var_avoirs_6m, f.var_avoirs_12m,
                f.var_flux_crediteurs_1m, f.var_flux_crediteurs_3m, f.var_flux_crediteurs_6m, f.var_flux_crediteurs_12m,
                f.var_flux_debiteurs_1m, f.var_flux_debiteurs_3m, f.var_flux_debiteurs_6m, f.var_flux_debiteurs_12m,
                1, NOW()
            FROM tmp_attrition_current_features AS f
            WHERE NOT EXISTS (
                SELECT 1
                FROM dm_attrition_variables AS old
                WHERE old.radical_compte = f.radical_compte
                  AND old.attrition = 1
            )
            ON CONFLICT (radical_compte, annee_mois) DO UPDATE SET
                statut_client_snapshot = EXCLUDED.statut_client_snapshot,
                avoirs = EXCLUDED.avoirs,
                flux_crediteurs = EXCLUDED.flux_crediteurs,
                flux_debiteurs = EXCLUDED.flux_debiteurs,
                var_avoirs_1m = EXCLUDED.var_avoirs_1m,
                var_avoirs_3m = EXCLUDED.var_avoirs_3m,
                var_avoirs_6m = EXCLUDED.var_avoirs_6m,
                var_avoirs_12m = EXCLUDED.var_avoirs_12m,
                var_flux_crediteurs_1m = EXCLUDED.var_flux_crediteurs_1m,
                var_flux_crediteurs_3m = EXCLUDED.var_flux_crediteurs_3m,
                var_flux_crediteurs_6m = EXCLUDED.var_flux_crediteurs_6m,
                var_flux_crediteurs_12m = EXCLUDED.var_flux_crediteurs_12m,
                var_flux_debiteurs_1m = EXCLUDED.var_flux_debiteurs_1m,
                var_flux_debiteurs_3m = EXCLUDED.var_flux_debiteurs_3m,
                var_flux_debiteurs_6m = EXCLUDED.var_flux_debiteurs_6m,
                var_flux_debiteurs_12m = EXCLUDED.var_flux_debiteurs_12m,
                attrition = 1,
                updated_at = NOW()
            """
        )
        return int(cur.rowcount or 0)


def append_scored_current_rows(conn) -> int:
    """Ajoute la photographie courante des clients scorés avec cible=0."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dm_attrition_variables (
                radical_compte, annee_mois, statut_client_snapshot,
                avoirs, flux_crediteurs, flux_debiteurs,
                var_avoirs_1m, var_avoirs_3m, var_avoirs_6m, var_avoirs_12m,
                var_flux_crediteurs_1m, var_flux_crediteurs_3m, var_flux_crediteurs_6m, var_flux_crediteurs_12m,
                var_flux_debiteurs_1m, var_flux_debiteurs_3m, var_flux_debiteurs_6m, var_flux_debiteurs_12m,
                attrition, updated_at
            )
            SELECT
                f.radical_compte, f.annee_mois, f.statut_client,
                f.avoirs, f.flux_crediteurs, f.flux_debiteurs,
                f.var_avoirs_1m, f.var_avoirs_3m, f.var_avoirs_6m, f.var_avoirs_12m,
                f.var_flux_crediteurs_1m, f.var_flux_crediteurs_3m, f.var_flux_crediteurs_6m, f.var_flux_crediteurs_12m,
                f.var_flux_debiteurs_1m, f.var_flux_debiteurs_3m, f.var_flux_debiteurs_6m, f.var_flux_debiteurs_12m,
                0, NOW()
            FROM tmp_attrition_current_features AS f
            ON CONFLICT (radical_compte, annee_mois) DO UPDATE SET
                statut_client_snapshot = EXCLUDED.statut_client_snapshot,
                avoirs = EXCLUDED.avoirs,
                flux_crediteurs = EXCLUDED.flux_crediteurs,
                flux_debiteurs = EXCLUDED.flux_debiteurs,
                var_avoirs_1m = EXCLUDED.var_avoirs_1m,
                var_avoirs_3m = EXCLUDED.var_avoirs_3m,
                var_avoirs_6m = EXCLUDED.var_avoirs_6m,
                var_avoirs_12m = EXCLUDED.var_avoirs_12m,
                var_flux_crediteurs_1m = EXCLUDED.var_flux_crediteurs_1m,
                var_flux_crediteurs_3m = EXCLUDED.var_flux_crediteurs_3m,
                var_flux_crediteurs_6m = EXCLUDED.var_flux_crediteurs_6m,
                var_flux_crediteurs_12m = EXCLUDED.var_flux_crediteurs_12m,
                var_flux_debiteurs_1m = EXCLUDED.var_flux_debiteurs_1m,
                var_flux_debiteurs_3m = EXCLUDED.var_flux_debiteurs_3m,
                var_flux_debiteurs_6m = EXCLUDED.var_flux_debiteurs_6m,
                var_flux_debiteurs_12m = EXCLUDED.var_flux_debiteurs_12m,
                updated_at = NOW()
            WHERE dm_attrition_variables.attrition = 0
            """
        )
        return int(cur.rowcount or 0)


def prune_history(conn, *, max_rows_per_client: int = 12) -> int:
    """Conserve uniquement les N observations mensuelles les plus récentes par client."""
    limit = max(1, int(max_rows_per_client))
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH ranked AS (
                SELECT
                    radical_compte,
                    annee_mois,
                    ROW_NUMBER() OVER (
                        PARTITION BY radical_compte
                        ORDER BY annee_mois DESC
                    ) AS rn
                FROM dm_attrition_variables
            )
            DELETE FROM dm_attrition_variables AS v
            USING ranked AS r
            WHERE r.radical_compte = v.radical_compte
              AND r.annee_mois = v.annee_mois
              AND r.rn > %s
            """,
            (limit,),
        )
        return int(cur.rowcount or 0)
