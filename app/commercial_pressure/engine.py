from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List

from app.commercial_pressure.scoring import score_client_pressure
from app.commercial_pressure.bootstrap import bootstrap_pressure_fake_interactions
from app.storage.postgres_db import connection

logger = logging.getLogger(__name__)
LOCK_KEY = 88432026
HISTORY_MONTHS = 13


class CommercialPressureAlreadyRunningError(RuntimeError):
    pass


def _annee_mois(value: date) -> int:
    return value.year * 100 + value.month


def _month_floor(value: date, months_back: int) -> date:
    year = value.year
    month = value.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def _purge_old_scores(conn, run_date: date) -> int:
    keep_from = _month_floor(run_date, HISTORY_MONTHS - 1)
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM dm_commercial_pressure_scores WHERE date_scoring < %s",
            (keep_from,),
        )
        return int(cur.rowcount or 0)


def _fetch_due_clients(conn, month: int, *, limit: int, after_radical: str | None) -> List[Dict[str, Any]]:
    params: list[Any] = [month]
    after_sql = ""
    if after_radical:
        after_sql = "AND c.radical_compte > %s"
        params.append(after_radical)
    params.append(limit)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT c.radical_compte, c."STATUT_CLIENT", c."Region"
            FROM clients c
            LEFT JOIN dm_commercial_pressure_scores s
              ON s.radical_compte = c.radical_compte
             AND s.annee_mois = %s
            WHERE c."STATUT_CLIENT" IN ('Actif', 'Inactif')
              AND s.id IS NULL
              {after_sql}
            ORDER BY c.radical_compte
            LIMIT %s
            """,
            params,
        )
        rows = cur.fetchall()
    return [dict(row) if isinstance(row, dict) else {
        "radical_compte": row[0], "STATUT_CLIENT": row[1], "Region": row[2]
    } for row in rows]


def _has_real_interactions(conn, run_date: date) -> bool:
    window_start = run_date - timedelta(days=29)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM dm_best_channel_interactions
                WHERE source = 'reel'
                  AND observed_at >= %s::date
                  AND observed_at < (%s::date + INTERVAL '1 day')
            ) AS has_real
            """,
            (window_start, run_date),
        )
        row = cur.fetchone() or {}
    return bool(row.get("has_real") if isinstance(row, dict) else row[0])


def _fetch_interactions(conn, radicals: List[str], run_date: date, *, real_only: bool) -> Dict[str, List[Dict[str, Any]]]:
    if not radicals:
        return {}
    window_start = run_date - timedelta(days=29)
    source_sql = "AND source = 'reel'" if real_only else ""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT radical_compte, canal, resultat_bloc, observed_at
            FROM dm_best_channel_interactions
            WHERE radical_compte = ANY(%s)
              AND observed_at >= %s::date
              AND observed_at < (%s::date + INTERVAL '1 day')
              {source_sql}
            ORDER BY radical_compte, observed_at
            """,
            (radicals, window_start, run_date),
        )
        rows = cur.fetchall()
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        item = dict(row) if isinstance(row, dict) else {
            "radical_compte": row[0], "canal": row[1], "resultat_bloc": row[2], "observed_at": row[3]
        }
        grouped[str(item.get("radical_compte") or "")].append(item)
    return grouped


def run_commercial_pressure_cycle(*, run_date: date | None = None, trigger: str = "manual") -> Dict[str, Any]:
    run_date = run_date or date.today()
    month = _annee_mois(run_date)
    batch_size = max(1000, int(os.getenv("COMMERCIAL_PRESSURE_BATCH_SIZE", "20000") or "20000"))
    result: Dict[str, Any] = {
        "ok": True,
        "run_date": run_date.isoformat(),
        "annee_mois": month,
        "trigger": trigger,
    }

    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,))
            locked = bool((cur.fetchone() or {}).get("pg_try_advisory_lock"))
        if not locked:
            raise CommercialPressureAlreadyRunningError("Un cycle Pression commerciale est déjà en cours.")

        try:
            result["history_rows_pruned"] = _purge_old_scores(conn, run_date)
            conn.commit()
            result["bootstrap"] = bootstrap_pressure_fake_interactions(conn, run_date=run_date)
            if result["bootstrap"].get("reason") == "waiting_for_best_channel_history":
                result["skipped"] = True
                result["reason"] = "waiting_for_best_channel_history"
                return result

            real_only = _has_real_interactions(conn, run_date)
            result["interaction_source"] = "reel" if real_only else "fake_mvp"

            scored = 0
            after: str | None = None
            distribution: Dict[str, int] = {"Faible": 0, "Modere": 0, "Eleve": 0}
            logger.info(
                "Scoring pression commerciale démarré: run_date=%s month=%s batch_size=%s",
                run_date.isoformat(), month, batch_size,
            )

            while True:
                clients = _fetch_due_clients(conn, month, limit=batch_size, after_radical=after)
                if not clients:
                    break
                radicals = [str(client.get("radical_compte") or "") for client in clients]
                interactions = _fetch_interactions(conn, radicals, run_date, real_only=real_only)

                score_rows = []
                client_updates = []
                for client in clients:
                    radical = str(client.get("radical_compte") or "")
                    metrics = score_client_pressure(interactions.get(radical, []), run_date=run_date)
                    level = str(metrics["niveau_pression"])
                    distribution[level] = distribution.get(level, 0) + 1
                    score_rows.append((
                        radical,
                        run_date,
                        month,
                        metrics["window_start"],
                        metrics["window_end"],
                        str(client.get("STATUT_CLIENT") or ""),
                        str(client.get("Region") or "Non renseignée"),
                        metrics["score_pression"],
                        level,
                        metrics["regle_niveau"],
                        metrics["nb_actions_7j"],
                        metrics["nb_actions_30j"],
                        metrics["nb_interactions_humaines_7j"],
                        metrics["nb_canaux_7j"],
                        metrics["nb_canaux_30j"],
                        metrics["dernier_contact"],
                    ))
                    client_updates.append((level, radical))

                with conn.cursor() as cur:
                    cur.executemany(
                        """
                        INSERT INTO dm_commercial_pressure_scores (
                            radical_compte, date_scoring, annee_mois,
                            window_start, window_end,
                            statut_client_snapshot, region,
                            score_pression, niveau_pression, regle_niveau,
                            nb_actions_7j, nb_actions_30j,
                            nb_interactions_humaines_7j,
                            nb_canaux_7j, nb_canaux_30j, dernier_contact
                        ) VALUES (
                            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                        )
                        ON CONFLICT (radical_compte, annee_mois) DO NOTHING
                        """,
                        score_rows,
                    )
                    cur.executemany(
                        """
                        UPDATE clients
                        SET "Pression_commerciale" = %s
                        WHERE radical_compte = %s
                        """,
                        client_updates,
                    )
                conn.commit()

                scored += len(clients)
                after = radicals[-1] if radicals else after
                logger.info(
                    "Scoring pression commerciale progression: clients_scores=%s dernier_radical=%s",
                    scored, after,
                )
                if len(clients) < batch_size:
                    break

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE clients
                    SET "Pression_commerciale" = 'non_score'
                    WHERE "STATUT_CLIENT" NOT IN ('Actif', 'Inactif')
                       OR "STATUT_CLIENT" IS NULL
                    """
                )
                cleared = int(cur.rowcount or 0)
                cur.execute(
                    """
                    SELECT niveau_pression, COUNT(*) AS clients
                    FROM dm_commercial_pressure_scores
                    WHERE annee_mois = %s
                    GROUP BY niveau_pression
                    """,
                    (month,),
                )
                current_distribution = {
                    str(row.get("niveau_pression")): int(row.get("clients") or 0)
                    for row in cur.fetchall()
                }
                cur.execute(
                    "SELECT COUNT(*) AS total FROM dm_commercial_pressure_scores WHERE annee_mois = %s",
                    (month,),
                )
                total_month = int((cur.fetchone() or {}).get("total") or 0)
            conn.commit()

            result.update({
                "scored_clients": scored,
                "rows_current_month": total_month,
                "updated_clients": scored,
                "cleared_non_scored": cleared,
                "distribution_scored_now": distribution,
                "distribution_current_month": current_distribution,
            })
            logger.info("Scoring pression commerciale terminé: %s", result)
            return result
        finally:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
