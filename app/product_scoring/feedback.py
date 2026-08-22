from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from app.product_scoring.constants import APPETENCE_THRESHOLD, objective_product_from_column
from app.storage.postgres_db import connection

logger = logging.getLogger(__name__)


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _load_actions(id_modele: str) -> list[Dict[str, Any]]:
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT liste_action FROM modeles WHERE id_modele=%s LIMIT 1", (id_modele,))
            row = cur.fetchone()
    raw = (row or {}).get("liste_action") if row else None
    if isinstance(raw, list):
        return [dict(x) for x in raw if isinstance(x, dict)]
    try:
        data = json.loads(str(raw or "[]"))
    except Exception:
        return []
    return [dict(x) for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def objective_products_for_model(id_modele: str) -> list[tuple[str, str]]:
    """Retourne (objective_id_action, product_code) pour les objectifs produits.

    Le produit est déduit des conditions du bloc objectif : Epargne,
    Carte_Actuelle/Activation_carte, credit_conso/encours_conso,
    credit_immo/encours_immo.
    """
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for block in _load_actions(id_modele):
        if not bool(block.get("objectif")):
            continue
        objective_id = _norm(block.get("ID"))
        for cond in block.get("ObjectiveConditions") or []:
            if not isinstance(cond, dict):
                continue
            column = cond.get("column")
            if not column:
                field = _norm(cond.get("field"))
                if field.lower().startswith("client."):
                    column = field.split(".", 1)[1]
                else:
                    column = field
            product = objective_product_from_column(column)
            key = (objective_id, product or "")
            if product and key not in seen:
                seen.add(key)
                out.append((objective_id, product))
    return out


def _score_expr(product: str) -> str:
    return {
        "card": "s.appetence_carte",
        "conso": "s.appetence_conso",
        "immo": "s.appetence_immo",
        "epargne": "s.appetence_epargne",
    }[product]


def register_campaign_population(id_campagne: str, id_modele: str) -> Dict[str, Any]:
    objectives = objective_products_for_model(id_modele)
    if not objectives:
        return {"ok": True, "objectives": 0, "rows_inserted": 0}
    inserted = 0
    with connection() as conn:
        with conn.cursor() as cur:
            for objective_id, product in objectives:
                score_expr = _score_expr(product)
                cur.execute(
                    f"""
                    INSERT INTO dm_product_campaign_feedback (
                        score_id, id_campagne, id_modele, radical_compte,
                        product_code, objective_id_action, score_at_launch,
                        appetent_at_launch, next_best_product_at_launch,
                        campaign_assigned_at
                    )
                    SELECT
                        s.id, %s, %s, cc."Radical_compte", %s, %s,
                        {score_expr},
                        COALESCE({score_expr},0) >= %s,
                        s.next_best_product,
                        NOW()
                    FROM clients_campagnes cc
                    JOIN LATERAL (
                        SELECT ps.*
                        FROM dm_product_scores ps
                        WHERE ps.radical_compte=cc."Radical_compte"
                        ORDER BY ps.annee_mois DESC
                        LIMIT 1
                    ) s ON TRUE
                    WHERE cc."ID_CAMPAGNE"=%s
                    ON CONFLICT (id_campagne, radical_compte, product_code, objective_id_action)
                    DO NOTHING
                    """,
                    (id_campagne, id_modele, product, objective_id, APPETENCE_THRESHOLD, id_campagne),
                )
                inserted += max(0, int(cur.rowcount or 0))
    if inserted:
        logger.info("Feedback produits campagne enregistré: campaign=%s objectives=%s rows=%s", id_campagne, len(objectives), inserted)
    return {"ok": True, "objectives": len(objectives), "rows_inserted": inserted}


def mark_campaign_contacted(conn, rid: int, *, contacted_at: str | None = None) -> int:
    """Marque un vrai contact après l'exécution d'un bloc de communication.

    L'affectation à une campagne seule ne compte pas comme un contact pour
    l'apprentissage des modèles produits.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT "ID_CAMPAGNE" AS id_campagne, "Radical_compte" AS radical_compte
        FROM clients_campagnes
        WHERE id=%s
        LIMIT 1
        """,
        (int(rid),),
    )
    row = cur.fetchone()
    if not row:
        return 0
    id_campagne = _norm(row.get("id_campagne"))
    radical = _norm(row.get("radical_compte"))
    if not id_campagne or not radical:
        return 0
    cur.execute(
        """
        UPDATE dm_product_campaign_feedback
        SET was_contacted=TRUE,
            contacted_at=COALESCE(contacted_at, %s::timestamptz, NOW()),
            updated_at=NOW()
        WHERE id_campagne=%s
          AND radical_compte=%s
          AND was_contacted=FALSE
        """,
        (contacted_at, id_campagne, radical),
    )
    return max(0, int(cur.rowcount or 0))


def _campaign_context_by_rid(conn, rid: int) -> tuple[str, str, str] | None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT cc."ID_CAMPAGNE" AS id_campagne, cc."Radical_compte" AS radical_compte,
               c.id_modele AS id_modele
        FROM clients_campagnes cc
        JOIN campagnes c ON c.id_campagne=cc."ID_CAMPAGNE"
        WHERE cc.id=%s
        LIMIT 1
        """,
        (int(rid),),
    )
    row = cur.fetchone()
    if not row:
        return None
    return (_norm(row.get("id_campagne")), _norm(row.get("id_modele")), _norm(row.get("radical_compte")))


def record_objective_feedback(conn, rid: int, *, objective_id_action: str, achieved: int) -> int:
    context = _campaign_context_by_rid(conn, rid)
    if not context:
        return 0
    id_campagne, id_modele, radical = context
    matches = [p for oid, p in objective_products_for_model(id_modele) if _norm(oid) == _norm(objective_id_action)]
    if not matches:
        return 0
    cur = conn.cursor()
    total = 0
    for product in matches:
        cur.execute(
            """
            UPDATE dm_product_campaign_feedback
            SET objective_achieved=%s,
                objective_result_at=NOW(),
                updated_at=NOW()
            WHERE id_campagne=%s
              AND radical_compte=%s
              AND product_code=%s
              AND objective_id_action=%s
              AND objective_achieved IS NULL
            """,
            (1 if int(achieved) else 0, id_campagne, radical, product, _norm(objective_id_action)),
        )
        total += max(0, int(cur.rowcount or 0))
    return total


def finalize_campaign_feedback(id_campagne: str) -> int:
    """Une campagne terminée transforme les objectifs produits non atteints en 0."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dm_product_campaign_feedback
                SET objective_achieved=0,
                    objective_result_at=COALESCE(objective_result_at,NOW()),
                    updated_at=NOW()
                WHERE id_campagne=%s
                  AND objective_achieved IS NULL
                """,
                (id_campagne,),
            )
            return max(0, int(cur.rowcount or 0))
