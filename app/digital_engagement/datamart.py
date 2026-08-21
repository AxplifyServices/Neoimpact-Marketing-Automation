from __future__ import annotations

import hashlib
import logging
import math
import os
import random
from datetime import date
from typing import Any, Dict, Iterable, List, Tuple

from faker import Faker

from app.storage.postgres_db import connection

logger = logging.getLogger(__name__)
_FAKE = Faker("fr_FR")

MAX_HISTORY_MONTHS = 15
DEFAULT_BATCH_SIZE = 5000


def current_annee_mois(run_date: date | None = None) -> int:
    current = run_date or date.today()
    return current.year * 100 + current.month


def shift_month(annee_mois: int, offset: int) -> int:
    year = int(annee_mois) // 100
    month = int(annee_mois) % 100
    absolute = year * 12 + (month - 1) + int(offset)
    return (absolute // 12) * 100 + (absolute % 12) + 1


def _stable_seed(radical_compte: str, annee_mois: int) -> int:
    digest = hashlib.blake2b(
        f"{radical_compte}:{annee_mois}:digital-engagement".encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big", signed=False)


def _fake_month_values(
    *,
    radical_compte: str,
    annee_mois: int,
    statut_client: str,
    app_installed: str,
    premiere_connex: str,
    nb_transaction: float,
) -> Tuple[int, float, float | None]:
    """Produit une photographie mensuelle synthétique, sans créer de client.

    Faker est utilisé comme générateur pseudo-aléatoire, seedé par
    radical_compte×mois pour rendre la donnée reproductible.
    """
    seed = _stable_seed(radical_compte, annee_mois)
    fake = _FAKE
    fake.seed_instance(seed)
    rng = random.Random(seed)

    installed = str(app_installed or "").strip().lower() == "oui"
    connected = str(premiere_connex or "").strip().lower() == "oui"
    status = str(statut_client or "").strip().lower()
    activity = max(0.0, float(nb_transaction or 0.0))

    if not installed:
        monthly = fake.random_int(min=0, max=3)
    elif not connected:
        monthly = fake.random_int(min=0, max=8)
    elif status == "inactif":
        monthly = fake.random_int(min=1, max=45)
    else:
        # Les transactions donnent seulement un léger signal de cohérence à la
        # fake data ; elles ne font pas partie du score final.
        upper = min(240, max(35, int(70 + activity * 0.35)))
        monthly = fake.random_int(min=8, max=upper)

    daily_average = float(monthly) / 30.0

    if monthly <= 0:
        weighted_hour = None
    else:
        # Profil dominant stable par client/mois.
        profile = fake.random_element(elements=("morning", "afternoon", "evening"))
        center = {"morning": 9.0, "afternoon": 15.0, "evening": 20.0}[profile]
        jitter = rng.uniform(-1.8, 1.8)
        weighted_hour = max(0.0, min(23.99, center + jitter))

    return int(monthly), daily_average, weighted_hour


def ensure_month_data(*, annee_mois: int | None = None) -> Dict[str, Any]:
    month = int(annee_mois or current_annee_mois())
    batch_size = max(
        1000,
        min(20000, int(os.getenv("DIGITAL_ENGAGEMENT_FAKE_BATCH_SIZE", str(DEFAULT_BATCH_SIZE)) or DEFAULT_BATCH_SIZE)),
    )

    inserted = 0
    processed = 0
    after_radical = ""

    with connection() as conn:
        while True:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        c.radical_compte,
                        c."STATUT_CLIENT",
                        c."Region",
                        c."App_instaled",
                        c."Premiere_connex",
                        COALESCE(c.nb_transaction, 0)
                    FROM clients AS c
                    WHERE LOWER(BTRIM(COALESCE(c."STATUT_CLIENT", ''))) IN (LOWER('Actif'), LOWER('Inactif'))
                      AND c.radical_compte > %s
                      AND NOT EXISTS (
                            SELECT 1
                            FROM dm_engagement_digital_variables AS v
                            WHERE v.radical_compte = c.radical_compte
                              AND v.annee_mois = %s
                      )
                    ORDER BY c.radical_compte
                    LIMIT %s
                    """,
                    (after_radical, month, batch_size),
                )
                rows = cur.fetchall()

            if not rows:
                break

            payload: List[Tuple[Any, ...]] = []
            for row in rows:
                radical = str(row[0])
                monthly, daily_avg, weighted_hour = _fake_month_values(
                    radical_compte=radical,
                    annee_mois=month,
                    statut_client=str(row[1] or ""),
                    app_installed=str(row[3] or ""),
                    premiere_connex=str(row[4] or ""),
                    nb_transaction=float(row[5] or 0),
                )
                payload.append(
                    (
                        radical,
                        month,
                        row[1],
                        row[2],
                        monthly,
                        daily_avg,
                        weighted_hour,
                    )
                )

            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO dm_engagement_digital_variables (
                        radical_compte,
                        annee_mois,
                        statut_client_snapshot,
                        region,
                        nb_connexions_mois,
                        moyenne_connexions_jour,
                        heure_moyenne_ponderee,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (radical_compte, annee_mois) DO NOTHING
                    """,
                    payload,
                )
                inserted += int(cur.rowcount or 0)

            processed += len(rows)
            after_radical = str(rows[-1][0])

        # Le datamart "variables" reste borné à 15 mois.
        threshold = shift_month(month, -(MAX_HISTORY_MONTHS - 1))
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM dm_engagement_digital_variables
                WHERE annee_mois < %s
                """,
                (threshold,),
            )
            pruned = int(cur.rowcount or 0)

            cur.execute(
                """
                SELECT COUNT(*)
                FROM dm_engagement_digital_variables
                WHERE annee_mois = %s
                """,
                (month,),
            )
            current_rows = int((cur.fetchone() or [0])[0] or 0)

    logger.info(
        "Datamart engagement prêt: month=%s rows=%s inserted=%s pruned=%s",
        month,
        current_rows,
        inserted,
        pruned,
    )
    return {
        "ok": True,
        "annee_mois": month,
        "processed_clients": processed,
        "rows_inserted": inserted,
        "rows_current_month": current_rows,
        "rows_pruned": pruned,
        "min_month_kept": threshold,
    }
