from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import date
from typing import Any, Dict

import numpy as np

from app.attrition.datamart import (
    append_scored_current_rows,
    create_current_feature_table,
    current_annee_mois,
    ensure_fake_history_if_empty,
    materialize_new_ruptures,
    prune_history,
)
from app.attrition.model import FEATURES, MODEL_CODE, get_or_train_model, matrix_from_rows, model_exists
from app.storage.postgres_db import connection

logger = logging.getLogger(__name__)

ATTRITION_ADVISORY_LOCK = 774_821_2026


class AttritionAlreadyRunningError(RuntimeError):
    pass


def _risk_threshold() -> float:
    value = float(os.getenv("ATTRITION_RISK_THRESHOLD", "0.5") or "0.5")
    if value < 0 or value > 1:
        raise RuntimeError("ATTRITION_RISK_THRESHOLD doit être compris entre 0 et 1.")
    return value


def _batch_size() -> int:
    return max(1_000, min(100_000, int(os.getenv("ATTRITION_SCORE_BATCH_SIZE", "25000") or "25000")))


def _current_month_complete(conn, *, annee_mois: int) -> bool:
    if not model_exists():
        return False
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM clients AS c
            WHERE LOWER(BTRIM(COALESCE(c."STATUT_CLIENT", ''))) IN (LOWER('Actif'), LOWER('Inactif'))
              AND NOT EXISTS (
                    SELECT 1
                    FROM dm_attrition_scores AS s
                    WHERE s.radical_compte = c.radical_compte
                      AND s.annee_mois = %s
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
              AND "Risque_attrition" = 'Oui'
            """
        )
        stale_flags = int((cur.fetchone() or [0])[0] or 0)
        cur.execute(
            """
            SELECT COUNT(*)
            FROM dm_attrition_scores AS s
            JOIN clients AS c ON c.radical_compte = s.radical_compte
            WHERE s.annee_mois = %s
              AND LOWER(BTRIM(COALESCE(c."STATUT_CLIENT", ''))) NOT IN (LOWER('Actif'), LOWER('Inactif'))
            """,
            (annee_mois,),
        )
        stale_scores = int((cur.fetchone() or [0])[0] or 0)
    return missing == 0 and stale_flags == 0 and stale_scores == 0


def _score_current_population(conn, booster, *, annee_mois: int, run_date: date, threshold: float) -> Dict[str, Any]:
    import xgboost as xgb

    feature_count = create_current_feature_table(
        conn,
        annee_mois=annee_mois,
        include_statuses=["Actif", "Inactif"],
    )

    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS tmp_attrition_predictions")
        cur.execute(
            """
            CREATE TEMP TABLE tmp_attrition_predictions (
                radical_compte TEXT PRIMARY KEY,
                score_attrition DOUBLE PRECISION NOT NULL
            ) ON COMMIT DROP
            """
        )

        select_cols = ", ".join(FEATURES)
        cur.execute(
            f"""
            SELECT radical_compte, {select_cols}
            FROM tmp_attrition_current_features
            ORDER BY radical_compte
            """
        )

        scored = 0
        risk_count = 0
        batch_size = _batch_size()
        while True:
            rows = cur.fetchmany(batch_size)
            if not rows:
                break
            x = matrix_from_rows(rows, feature_offset=1)
            dmatrix = xgb.DMatrix(x, feature_names=FEATURES)
            predictions = booster.predict(dmatrix)
            payload = [(str(row[0]), float(score)) for row, score in zip(rows, predictions)]
            risk_count += int((predictions >= threshold).sum())

            with conn.cursor() as writer:
                with writer.copy(
                    "COPY tmp_attrition_predictions (radical_compte, score_attrition) FROM STDIN"
                ) as copy:
                    for item in payload:
                        copy.write_row(item)
            scored += len(payload)

    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM dm_attrition_scores AS s
            USING clients AS c
            WHERE s.radical_compte = c.radical_compte
              AND s.annee_mois = %s
              AND LOWER(BTRIM(COALESCE(c."STATUT_CLIENT", ''))) NOT IN (LOWER('Actif'), LOWER('Inactif'))
            """,
            (annee_mois,),
        )
        cur.execute(
            """
            INSERT INTO dm_attrition_scores (
                radical_compte, annee_mois, date_scoring,
                statut_client_snapshot, region,
                score_attrition, risque_attrition, seuil_risque, modele, created_at
            )
            SELECT
                f.radical_compte,
                %s,
                %s,
                f.statut_client,
                f.region,
                p.score_attrition,
                CASE WHEN p.score_attrition >= %s THEN 'Oui' ELSE 'Non' END,
                %s,
                %s,
                NOW()
            FROM tmp_attrition_current_features AS f
            JOIN tmp_attrition_predictions AS p USING (radical_compte)
            ON CONFLICT (radical_compte, annee_mois) DO UPDATE SET
                date_scoring = EXCLUDED.date_scoring,
                statut_client_snapshot = EXCLUDED.statut_client_snapshot,
                region = EXCLUDED.region,
                score_attrition = EXCLUDED.score_attrition,
                risque_attrition = EXCLUDED.risque_attrition,
                seuil_risque = EXCLUDED.seuil_risque,
                modele = EXCLUDED.modele,
                created_at = NOW()
            """,
            (annee_mois, run_date, threshold, threshold, MODEL_CODE),
        )
        score_rows = int(cur.rowcount or 0)

        cur.execute(
            """
            UPDATE clients AS c
            SET "Risque_attrition" = CASE
                WHEN p.score_attrition >= %s THEN 'Oui'
                ELSE 'Non'
            END
            FROM tmp_attrition_predictions AS p
            WHERE p.radical_compte = c.radical_compte
              AND c."Risque_attrition" IS DISTINCT FROM CASE
                    WHEN p.score_attrition >= %s THEN 'Oui'
                    ELSE 'Non'
                  END
            """,
            (threshold, threshold),
        )
        updated_clients = int(cur.rowcount or 0)

        # Les prospects et clients déjà en rupture ne sont pas à prédire.
        cur.execute(
            """
            UPDATE clients
            SET "Risque_attrition" = 'Non'
            WHERE LOWER(BTRIM(COALESCE("STATUT_CLIENT", ''))) NOT IN (LOWER('Actif'), LOWER('Inactif'))
              AND "Risque_attrition" IS DISTINCT FROM 'Non'
            """
        )
        cleared_non_scored = int(cur.rowcount or 0)

    appended = append_scored_current_rows(conn)
    return {
        "feature_rows": feature_count,
        "scored_clients": scored,
        "risk_clients": risk_count,
        "score_rows": score_rows,
        "updated_clients": updated_clients,
        "cleared_non_scored": cleared_non_scored,
        "history_rows_appended": appended,
    }


def run_attrition_cycle(
    *,
    annee_mois: int | None = None,
    run_date: date | None = None,
    force: bool = False,
) -> Dict[str, Any]:
    month = int(annee_mois or current_annee_mois(run_date))
    today = run_date or date.today()
    threshold = _risk_threshold()

    bootstrap = ensure_fake_history_if_empty(annee_mois=month)

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_xact_lock(%s)", (ATTRITION_ADVISORY_LOCK,))
            locked = bool((cur.fetchone() or [False])[0])
            if not locked:
                raise AttritionAlreadyRunningError("Un scoring attrition est déjà en cours.")

        new_ruptures = materialize_new_ruptures(conn, annee_mois=month)
        pruned_before_scoring = prune_history(conn, max_rows_per_client=12)

        if not force and _current_month_complete(conn, annee_mois=month):
            return {
                "ok": True,
                "skipped": True,
                "reason": "already_scored_current_month",
                "annee_mois": month,
                "run_date": str(today),
                "bootstrap": bootstrap,
                "new_ruptures": new_ruptures,
                "history_rows_pruned": pruned_before_scoring,
                "model_found": True,
            }

        booster, metadata, trained_now = get_or_train_model(conn)
        scoring = _score_current_population(
            conn,
            booster,
            annee_mois=month,
            run_date=today,
            threshold=threshold,
        )
        pruned_after_scoring = prune_history(conn, max_rows_per_client=12)

    return {
        "ok": True,
        "skipped": False,
        "annee_mois": month,
        "run_date": str(today),
        "bootstrap": bootstrap,
        "new_ruptures": new_ruptures,
        "history_rows_pruned": pruned_before_scoring + pruned_after_scoring,
        "model_found": not trained_now,
        "model_trained_now": trained_now,
        "model": {
            "code": metadata.get("model_code", MODEL_CODE),
            "trained_at": metadata.get("trained_at"),
            "training_rows": metadata.get("training_rows"),
            "positive_rows_total": metadata.get("positive_rows_total"),
            "validation_auc": metadata.get("validation_auc"),
            "validation_precision": metadata.get("validation_precision"),
            "validation_recall": metadata.get("validation_recall"),
        },
        "threshold": threshold,
        **scoring,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Moteur mensuel de scoring attrition")
    parser.add_argument("--month", type=int, dest="annee_mois")
    parser.add_argument("--date", dest="run_date")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    run_date = date.fromisoformat(args.run_date) if args.run_date else None
    result = run_attrition_cycle(
        annee_mois=args.annee_mois,
        run_date=run_date,
        force=bool(args.force),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
