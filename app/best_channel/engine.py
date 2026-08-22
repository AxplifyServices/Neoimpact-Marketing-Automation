from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any, Dict, List

from app.best_channel.bootstrap import bootstrap_fake_interactions
from app.best_channel.history import age_band, finalize_terminated_sequences
from app.best_channel.model import MODEL_CODE, get_or_train_model, score_client_batch
from app.storage.postgres_db import connection

logger = logging.getLogger(__name__)
LOCK_KEY = 88422026


class BestChannelAlreadyRunningError(RuntimeError):
    pass


def _annee_mois(value: date) -> int:
    return value.year * 100 + value.month


def _purge_old_interactions(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM dm_best_channel_interactions
            WHERE observed_at < CURRENT_DATE - INTERVAL '12 months'
            """
        )
        return int(cur.rowcount or 0)


def _fetch_due_clients(conn, run_date: date, *, limit: int, after_radical: str | None) -> List[Dict[str, Any]]:
    # Version explicite pour éviter tout décalage de placeholders selon la pagination.
    with conn.cursor() as cur:
        if after_radical:
            cur.execute(
                """
                SELECT c.radical_compte, c."Age", c."Region", c."STATUT_CLIENT",
                       MAX(s.date_scoring) AS last_scoring
                FROM clients c
                LEFT JOIN dm_best_channel_scores s ON s.radical_compte = c.radical_compte
                WHERE c."STATUT_CLIENT" IN ('Actif', 'Inactif')
                  AND c.radical_compte > %s
                GROUP BY c.radical_compte, c."Age", c."Region", c."STATUT_CLIENT"
                HAVING MAX(s.date_scoring) IS NULL
                    OR MAX(s.date_scoring) <= (%s::date - INTERVAL '6 months')
                ORDER BY c.radical_compte
                LIMIT %s
                """,
                (after_radical, run_date, limit),
            )
        else:
            cur.execute(
                """
                SELECT c.radical_compte, c."Age", c."Region", c."STATUT_CLIENT",
                       MAX(s.date_scoring) AS last_scoring
                FROM clients c
                LEFT JOIN dm_best_channel_scores s ON s.radical_compte = c.radical_compte
                WHERE c."STATUT_CLIENT" IN ('Actif', 'Inactif')
                GROUP BY c.radical_compte, c."Age", c."Region", c."STATUT_CLIENT"
                HAVING MAX(s.date_scoring) IS NULL
                    OR MAX(s.date_scoring) <= (%s::date - INTERVAL '6 months')
                ORDER BY c.radical_compte
                LIMIT %s
                """,
                (run_date, limit),
            )
        rows = cur.fetchall()
    return [dict(row) if isinstance(row, dict) else {
        "radical_compte": row[0], "Age": row[1], "Region": row[2],
        "STATUT_CLIENT": row[3], "last_scoring": row[4]
    } for row in rows]


def run_best_channel_cycle(*, run_date: date | None = None, trigger: str = "manual") -> Dict[str, Any]:
    run_date = run_date or date.today()
    batch_size = max(1000, int(os.getenv("BEST_CHANNEL_SCORE_BATCH_SIZE", "20000") or "20000"))
    result: Dict[str, Any] = {
        "ok": True,
        "run_date": run_date.isoformat(),
        "annee_mois": _annee_mois(run_date),
        "trigger": trigger,
    }

    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,))
            locked = bool((cur.fetchone() or {}).get("pg_try_advisory_lock"))
        if not locked:
            raise BestChannelAlreadyRunningError("Un cycle Best Channel est déjà en cours.")
        try:
            result["history_rows_pruned"] = _purge_old_interactions(conn)
            result["terminal_rows_finalized"] = finalize_terminated_sequences(conn)

            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM dm_best_channel_interactions WHERE finalized_at IS NOT NULL")
                finalized = int(next(iter((cur.fetchone() or {"count": 0}).values())) or 0)
            if finalized == 0:
                result["bootstrap"] = bootstrap_fake_interactions(conn, run_date=run_date)
            else:
                result["bootstrap"] = {"ok": True, "bootstrapped": False, "rows": finalized}

            booster, metadata, trained_now = get_or_train_model(conn)
            result["model_found"] = not trained_now
            result["model_trained_now"] = trained_now
            result["model"] = {
                "code": metadata.get("model_code", MODEL_CODE),
                "trained_at": metadata.get("trained_at"),
                "training_rows": metadata.get("training_rows"),
                "positive_rows": metadata.get("positive_rows"),
                "validation_auc": metadata.get("validation_auc"),
            }

            scored = 0
            after: str | None = None
            top1_counts: Dict[str, int] = {}
            logger.info(
                "Scoring Best Channel démarré: run_date=%s batch_size=%s",
                run_date.isoformat(),
                batch_size,
            )
            while True:
                clients = _fetch_due_clients(conn, run_date, limit=batch_size, after_radical=after)
                if not clients:
                    break
                score_rows = []
                update_rows = []
                profiles = [
                    (
                        age_band(client.get("Age")),
                        str(client.get("Region") or "Inconnue"),
                    )
                    for client in clients
                ]
                rankings = score_client_batch(booster, metadata, profiles)
                for client, (tranche, region), ranking in zip(clients, profiles, rankings):
                    radical = str(client.get("radical_compte") or "")
                    top = ranking[:3]
                    while len(top) < 3:
                        top.append(("non_score", 0.0))
                    score_rows.append((
                        radical, run_date, _annee_mois(run_date), str(client.get("STATUT_CLIENT") or ""),
                        tranche, region,
                        top[0][0], top[0][1], top[1][0], top[1][1], top[2][0], top[2][1],
                        metadata.get("model_code", MODEL_CODE),
                    ))
                    update_rows.append((top[0][0], top[1][0], top[2][0], radical))
                    top1_counts[top[0][0]] = top1_counts.get(top[0][0], 0) + 1

                with conn.cursor() as cur:
                    cur.executemany(
                        """
                        INSERT INTO dm_best_channel_scores (
                            radical_compte, date_scoring, annee_mois, statut_client_snapshot,
                            tranche_age, region,
                            canal_top1, score_top1, canal_top2, score_top2, canal_top3, score_top3,
                            modele
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (radical_compte, date_scoring) DO UPDATE SET
                            canal_top1=EXCLUDED.canal_top1, score_top1=EXCLUDED.score_top1,
                            canal_top2=EXCLUDED.canal_top2, score_top2=EXCLUDED.score_top2,
                            canal_top3=EXCLUDED.canal_top3, score_top3=EXCLUDED.score_top3,
                            modele=EXCLUDED.modele
                        """,
                        score_rows,
                    )
                    cur.executemany(
                        """
                        UPDATE clients
                        SET "Canal_top1"=%s, "Canal_top2"=%s, "Canal_top3"=%s
                        WHERE radical_compte=%s
                        """,
                        update_rows,
                    )
                conn.commit()
                scored += len(clients)
                after = str(clients[-1].get("radical_compte") or "")
                logger.info(
                    "Scoring Best Channel progression: clients_scores=%s dernier_radical=%s",
                    scored,
                    after,
                )
                if len(clients) < batch_size:
                    break

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE clients
                    SET "Canal_top1"='non_score', "Canal_top2"='non_score', "Canal_top3"='non_score'
                    WHERE "STATUT_CLIENT" NOT IN ('Actif','Inactif')
                       OR "STATUT_CLIENT" IS NULL
                    """
                )
                cleared = int(cur.rowcount or 0)
            result["scored_clients"] = scored
            result["updated_clients"] = scored
            result["cleared_non_scored"] = cleared
            result["top1_distribution"] = top1_counts
            return result
        finally:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
