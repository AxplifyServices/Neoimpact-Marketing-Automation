from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any, Dict, List

from app.product_scoring.bootstrap import ensure_fake_training_history
from app.product_scoring.constants import CARD_PRODUCTS, CARD_RANK, MODEL_VERSION, PRODUCT_LABELS
from app.product_scoring.features import ensure_current_snapshot, month_key
from app.product_scoring.model import MODEL_SPECS, ensure_models, predict
from app.storage.postgres_db import connection

logger = logging.getLogger(__name__)
ADVISORY_LOCK_KEY = 882_823_2026


class ProductScoringAlreadyRunningError(RuntimeError):
    pass


def _rows_for_product(rows: List[Dict[str, Any]], product: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    contacts_key = f"feedback_{product}_contacts_12m"
    conversions_key = f"feedback_{product}_conversions_12m"
    for row in rows:
        item = dict(row)
        item["feedback_contacts"] = item.get(contacts_key) or 0
        item["feedback_conversions"] = item.get(conversions_key) or 0
        out.append(item)
    return out


def _score_batch(rows: List[Dict[str, Any]]) -> List[tuple]:
    if not rows:
        return []
    # Cartes + épargne : un modèle binaire indépendant par produit.
    pred = {
        "card_silver": predict("card_silver", _rows_for_product(rows, "card")),
        "card_titanium": predict("card_titanium", _rows_for_product(rows, "card")),
        "card_platinium": predict("card_platinium", _rows_for_product(rows, "card")),
        "card_infinite": predict("card_infinite", _rows_for_product(rows, "card")),
        "epargne": predict("epargne", _rows_for_product(rows, "epargne")),
    }

    # Les crédits possèdent bien trois modèles par produit. On ne calcule un
    # modèle que sur les clients qui relèvent de son état d'équipement.
    conso_scores: Dict[int, float] = {}
    immo_scores: Dict[int, float] = {}
    for product, state_field, sink in (
        ("conso", "credit_conso_state", conso_scores),
        ("immo", "credit_immo_state", immo_scores),
    ):
        for state in ("never", "finished", "active"):
            indexes = [i for i, row in enumerate(rows) if str(row.get(state_field) or "never") == state]
            if not indexes:
                continue
            subset = [_rows_for_product([rows[i]], product)[0] for i in indexes]
            values = predict(f"{product}_{state}", subset)
            for idx, score in zip(indexes, values):
                sink[idx] = float(score)

    output: List[tuple] = []
    for i, row in enumerate(rows):
        current_rank = int(row.get("card_rank") or 0)
        card_values: Dict[str, float | None] = {}
        for card in CARD_PRODUCTS:
            code = f"card_{card.lower()}"
            if CARD_RANK[card] > current_rank:
                card_values[card] = float(pred[code][i])
            else:
                card_values[card] = None
        eligible_card_scores = [(c, s) for c, s in card_values.items() if s is not None]
        if eligible_card_scores:
            recommended_card, appetite_card = max(eligible_card_scores, key=lambda item: float(item[1] or 0.0))
        else:
            recommended_card, appetite_card = "non_score", None

        appetite_epargne = None if int(row.get("epargne_active") or 0) == 1 else float(pred["epargne"][i])
        appetite_conso = float(conso_scores.get(i, 0.0))
        appetite_immo = float(immo_scores.get(i, 0.0))
        candidates = []
        if appetite_card is not None:
            candidates.append(("Carte", float(appetite_card)))
        if appetite_conso is not None:
            candidates.append(("Credit conso", float(appetite_conso)))
        if appetite_immo is not None:
            candidates.append(("Credit immo", float(appetite_immo)))
        if appetite_epargne is not None:
            candidates.append(("Epargne", float(appetite_epargne)))
        nbp, nbp_score = max(candidates, key=lambda x: x[1]) if candidates else ("non_score", None)

        output.append((
            row.get("radical_compte"), row.get("statut_client"), row.get("region"),
            card_values["Silver"], card_values["Titanium"], card_values["Platinium"], card_values["Infinite"],
            CARD_RANK["Silver"] > current_rank, CARD_RANK["Titanium"] > current_rank,
            CARD_RANK["Platinium"] > current_rank, CARD_RANK["Infinite"] > current_rank,
            appetite_card, recommended_card,
            appetite_conso, str(row.get("credit_conso_state") or "never"),
            appetite_immo, str(row.get("credit_immo_state") or "never"),
            appetite_epargne, nbp, nbp_score,
        ))
    return output


def _score_clients(run_date: date) -> Dict[str, Any]:
    month = month_key(run_date)
    batch_size = max(1000, int(os.getenv("PRODUCT_SCORING_SCORE_BATCH_SIZE", "20000") or "20000"))
    scored = 0
    last_radical = ""
    nbp_distribution: Dict[str, int] = {}
    card_distribution: Dict[str, int] = {}
    logger.info("Scoring produits démarré: month=%s batch_size=%s", month, batch_size)
    while True:
        with connection(dict_rows=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM dm_product_training_monthly
                    WHERE annee_mois=%s
                      AND radical_compte > %s
                      AND statut_client IN ('Actif','Inactif')
                    ORDER BY radical_compte
                    LIMIT %s
                    """,
                    (month, last_radical, batch_size),
                )
                rows = [dict(row) for row in cur.fetchall()]
        if not rows:
            break
        values = _score_batch(rows)
        with connection() as conn:
            with conn.cursor() as cur:
                score_sql = """
                    INSERT INTO dm_product_scores (
                        radical_compte, date_scoring, annee_mois, statut_client_snapshot, region,
                        score_card_silver, score_card_titanium, score_card_platinium, score_card_infinite,
                        card_eligible_silver, card_eligible_titanium, card_eligible_platinium, card_eligible_infinite,
                        appetence_carte, carte_recommandee,
                        appetence_conso, conso_model_segment, appetence_immo, immo_model_segment,
                        appetence_epargne, next_best_product, next_best_product_score,
                        model_version_cards, model_version_conso, model_version_immo, model_version_epargne
                    ) VALUES (""" + ",".join(["%s"] * 26) + """)
                    ON CONFLICT (radical_compte, annee_mois) DO UPDATE SET
                        date_scoring=EXCLUDED.date_scoring,
                        statut_client_snapshot=EXCLUDED.statut_client_snapshot,
                        region=EXCLUDED.region,
                        score_card_silver=EXCLUDED.score_card_silver,
                        score_card_titanium=EXCLUDED.score_card_titanium,
                        score_card_platinium=EXCLUDED.score_card_platinium,
                        score_card_infinite=EXCLUDED.score_card_infinite,
                        card_eligible_silver=EXCLUDED.card_eligible_silver,
                        card_eligible_titanium=EXCLUDED.card_eligible_titanium,
                        card_eligible_platinium=EXCLUDED.card_eligible_platinium,
                        card_eligible_infinite=EXCLUDED.card_eligible_infinite,
                        appetence_carte=EXCLUDED.appetence_carte,
                        carte_recommandee=EXCLUDED.carte_recommandee,
                        appetence_conso=EXCLUDED.appetence_conso,
                        conso_model_segment=EXCLUDED.conso_model_segment,
                        appetence_immo=EXCLUDED.appetence_immo,
                        immo_model_segment=EXCLUDED.immo_model_segment,
                        appetence_epargne=EXCLUDED.appetence_epargne,
                        next_best_product=EXCLUDED.next_best_product,
                        next_best_product_score=EXCLUDED.next_best_product_score,
                        model_version_cards=EXCLUDED.model_version_cards,
                        model_version_conso=EXCLUDED.model_version_conso,
                        model_version_immo=EXCLUDED.model_version_immo,
                        model_version_epargne=EXCLUDED.model_version_epargne,
                        updated_at=NOW()
                """
                score_params = [
                    (
                        v[0], run_date, month, v[1], v[2],
                        v[3], v[4], v[5], v[6], v[7], v[8], v[9], v[10],
                        v[11], v[12], v[13], v[14], v[15], v[16], v[17], v[18], v[19],
                        MODEL_VERSION, MODEL_VERSION, MODEL_VERSION, MODEL_VERSION,
                    ) for v in values
                ]
                cur.executemany(score_sql, score_params)
                cur.executemany(
                    """
                    UPDATE clients SET
                        "Appetence_carte"=%s, "Carte_recommandee"=%s,
                        "Appetence_conso"=%s, "Appetence_immo"=%s, "Appetence_epargne"=%s,
                        "Next_best_product"=%s, "Next_best_product_score"=%s
                    WHERE radical_compte=%s
                    """,
                    [(v[11], v[12], v[13], v[15], v[17], v[18], v[19], v[0]) for v in values],
                )
        for v in values:
            nbp_distribution[str(v[18])] = nbp_distribution.get(str(v[18]), 0) + 1
            card_distribution[str(v[12])] = card_distribution.get(str(v[12]), 0) + 1
        scored += len(values)
        last_radical = str(rows[-1].get("radical_compte") or "")
        logger.info("Scoring produits progression: clients_scores=%s dernier_radical=%s", scored, last_radical)

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE clients SET
                    "Appetence_carte"=NULL, "Carte_recommandee"='non_score',
                    "Appetence_conso"=NULL, "Appetence_immo"=NULL, "Appetence_epargne"=NULL,
                    "Next_best_product"='non_score', "Next_best_product_score"=NULL
                WHERE COALESCE("STATUT_CLIENT",'') NOT IN ('Actif','Inactif')
                """
            )
            cleared = int(cur.rowcount or 0)
    return {"scored_clients": scored, "cleared_non_scored": cleared, "nbp_distribution": nbp_distribution, "card_distribution": card_distribution}


def run_product_scoring_cycle(*, trigger: str = "manual", run_date: date | None = None) -> Dict[str, Any]:
    day = run_date or date.today()
    with connection() as lock_conn:
        with lock_conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (ADVISORY_LOCK_KEY,))
            if not bool((cur.fetchone() or [False])[0]):
                raise ProductScoringAlreadyRunningError("Un scoring produits est déjà en cours.")
        try:
            bootstrap = ensure_fake_training_history(day)
            datamart = ensure_current_snapshot(day)
            models = ensure_models(day)
            month = month_key(day)
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM clients WHERE \"STATUT_CLIENT\" IN ('Actif','Inactif')")
                    eligible = int((cur.fetchone() or [0])[0] or 0)
                    cur.execute("SELECT COUNT(*) FROM dm_product_scores WHERE annee_mois=%s", (month,))
                    existing = int((cur.fetchone() or [0])[0] or 0)
            if eligible > 0 and existing >= eligible:
                return {
                    "ok": True, "skipped": True, "reason": "already_scored_current_month",
                    "trigger": trigger, "run_date": day.isoformat(), "annee_mois": month,
                    "bootstrap": bootstrap, "datamart": datamart,
                    "models": {k: {"auc": v.get("validation_auc"), "positive_rows": v.get("positive_rows")} for k, v in models.items()},
                    "scored_clients": 0,
                }
            result = _score_clients(day)
            summary = {
                "ok": True, "skipped": False, "trigger": trigger, "run_date": day.isoformat(), "annee_mois": month,
                "bootstrap": bootstrap, "datamart": datamart,
                "models": {k: {"auc": v.get("validation_auc"), "positive_rows": v.get("positive_rows")} for k, v in models.items()},
                **result,
            }
            logger.info("Scoring produits terminé: %s", summary)
            return summary
        finally:
            try:
                with lock_conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_KEY,))
            except Exception:
                pass
