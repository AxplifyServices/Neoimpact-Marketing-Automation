from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
from datetime import datetime
from typing import Any, Dict, Iterable, Optional
from zoneinfo import ZoneInfo

from faker import Faker
from psycopg.rows import dict_row

from app.storage.postgres_db import get_connection

logger = logging.getLogger(__name__)

TIMEZONE = "Africa/Casablanca"
DEFAULT_SEED = 20260821
DEFAULT_BATCH_SIZE = 5_000
MAX_MONTHS_PER_CLIENT = 15
TARGET_TABLE = "dm_segmentation_variables"
STAGE_TABLE = "tmp_dm_segmentation_variables_stage"
SEGMENTATION_DATAMART_ADVISORY_LOCK_KEY = 2_026_082_102


class SegmentationDatamartAlreadyRunningError(RuntimeError):
    """Une autre alimentation du datamart possède déjà le verrou global."""


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


def shift_month(yyyymm: int, delta: int) -> int:
    year = yyyymm // 100
    month = yyyymm % 100
    index = year * 12 + (month - 1) + delta
    target_year, target_month0 = divmod(index, 12)
    return target_year * 100 + target_month0 + 1


def month_distance(start_yyyymm: int, end_yyyymm: int) -> int:
    start_year, start_month = divmod(start_yyyymm, 100)
    end_year, end_month = divmod(end_yyyymm, 100)
    return (end_year - start_year) * 12 + (end_month - start_month)


def _stable_seed(global_seed: int, *parts: Any) -> int:
    payload = "|".join([str(global_seed), *(str(part) for part in parts)])
    digest = hashlib.blake2b(payload.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=False)


def _text_yes(value: Any) -> bool:
    return str(value or "").strip().lower() in {"oui", "yes", "1", "true"}


def _non_negative_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return max(0.0, parsed)


def _non_negative_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, parsed)


def _current_tenure_months(client: Dict[str, Any], *, global_seed: int) -> int:
    years = _non_negative_int(client.get("Anciennete"))
    # clients ne contient que l'ancienneté entière en années. Pour le MVP fake,
    # le mois résiduel est stable par client afin de ne pas changer à chaque run.
    residual = _stable_seed(global_seed, client["radical_compte"], "tenure") % 12
    return years * 12 + int(residual)


def _latent_salarie(client: Dict[str, Any], *, global_seed: int) -> bool:
    radical = str(client["radical_compte"])
    revenu = _non_negative_float(client.get("montant_revenu"))
    revenu_domicilie = _text_yes(client.get("revenu_domicilie"))
    probability = 0.88 if revenu_domicilie else 0.46
    if revenu < 2_000:
        probability *= 0.55
    # Tirage stable par client, jamais stocké : le moteur le redétecte ensuite
    # uniquement depuis fréquence + régularité des flux.
    unit = (_stable_seed(global_seed, radical, "latent_salarie") % 10_000_000) / 10_000_000.0
    return unit < probability


def _generate_month_values(
    client: Dict[str, Any],
    *,
    annee_mois: int,
    anciennete_mois: int,
    global_seed: int,
    fake: Faker,
) -> tuple[float, float, float]:
    if anciennete_mois <= 0:
        return 0.0, 0.0, 0.0

    radical = str(client["radical_compte"])
    fake.seed_instance(_stable_seed(global_seed, radical, annee_mois, "monthly"))
    rng = fake.random

    revenu = _non_negative_float(client.get("montant_revenu"))
    if revenu < 1.0:
        revenu = float(rng.triangular(1_500.0, 35_000.0, 6_500.0))

    solde_moyen = _non_negative_float(client.get("solde_moyen_depots"))
    latent_salarie = _latent_salarie(client, global_seed=global_seed)
    bp = _text_yes(client.get("BP"))

    base_avoirs = solde_moyen
    if base_avoirs < 1.0:
        base_avoirs = revenu * rng.uniform(0.7, 7.0)
    if bp:
        base_avoirs = max(base_avoirs, revenu * rng.uniform(18.0, 55.0))

    if latent_salarie:
        if rng.random() < 0.93:
            flux = revenu * rng.normalvariate(1.0, 0.065)
            if rng.random() < 0.08:
                flux *= rng.uniform(1.08, 1.35)
        else:
            flux = rng.uniform(0.0, min(1_900.0, revenu * 0.30))
    else:
        if rng.random() < 0.28:
            flux = rng.uniform(0.0, min(1_900.0, revenu * 0.40))
        else:
            flux = revenu * rng.lognormvariate(-0.12, 0.78)

    encours = base_avoirs * rng.lognormvariate(0.0, 0.13 if latent_salarie else 0.28)
    encours = max(0.0, encours)
    q10_factor = rng.uniform(0.32, 0.72) if latent_salarie else rng.uniform(0.48, 0.92)

    return (
        round(max(0.0, flux), 2),
        round(encours * q10_factor, 2),
        round(encours, 2),
    )


def _ensure_stage_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            CREATE TEMP TABLE IF NOT EXISTS {STAGE_TABLE} (
                radical_compte TEXT NOT NULL,
                annee_mois INTEGER NOT NULL,
                flux_crediteur_m DOUBLE PRECISION NOT NULL,
                moyenne_10pc_plus_petits DOUBLE PRECISION NOT NULL,
                encours_m_moyen DOUBLE PRECISION NOT NULL,
                anciennete_mois INTEGER NOT NULL
            ) ON COMMIT PRESERVE ROWS
            """
        )
        cur.execute(f"TRUNCATE TABLE {STAGE_TABLE}")


def _period_counts(conn, annee_mois: int) -> Dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM clients")
        clients = int((cur.fetchone() or [0])[0] or 0)
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM {TARGET_TABLE} AS d
            JOIN clients AS c USING (radical_compte)
            WHERE d.annee_mois = %s
            """,
            (annee_mois,),
        )
        current_rows = int((cur.fetchone() or [0])[0] or 0)
    return {"clients": clients, "current_rows": current_rows}


def _fetch_missing_client_batch(
    conn,
    *,
    annee_mois: int,
    after_radical: Optional[str],
    limit: int,
) -> list[Dict[str, Any]]:
    predicate = "" if after_radical is None else "AND c.radical_compte > %s"
    params: tuple[Any, ...]
    if after_radical is None:
        params = (annee_mois, annee_mois, limit)
    else:
        params = (annee_mois, annee_mois, after_radical, limit)

    query = f"""
        SELECT
            c.radical_compte,
            c."Anciennete" AS "Anciennete",
            c.montant_revenu,
            c.solde_moyen_depots,
            c.revenu_domicilie,
            c."BP" AS "BP",
            previous.annee_mois AS previous_month,
            previous.anciennete_mois AS previous_tenure
        FROM clients AS c
        LEFT JOIN LATERAL (
            SELECT d.annee_mois, d.anciennete_mois
            FROM {TARGET_TABLE} AS d
            WHERE d.radical_compte = c.radical_compte
              AND d.annee_mois < %s
            ORDER BY d.annee_mois DESC
            LIMIT 1
        ) AS previous ON TRUE
        WHERE NOT EXISTS (
            SELECT 1
            FROM {TARGET_TABLE} AS current_row
            WHERE current_row.radical_compte = c.radical_compte
              AND current_row.annee_mois = %s
        )
        {predicate}
        ORDER BY c.radical_compte
        LIMIT %s
    """

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def _rows_for_client(
    client: Dict[str, Any],
    *,
    target_month: int,
    global_seed: int,
    fake: Faker,
) -> Iterable[tuple[Any, ...]]:
    radical = str(client["radical_compte"])
    previous_month = client.get("previous_month")
    previous_tenure = client.get("previous_tenure")

    if previous_month is None:
        # Nouveau client du datamart : on construit immédiatement la fenêtre de
        # 15 mois. Les mois antérieurs à l'entrée en relation sont conservés à 0.
        current_tenure = _current_tenure_months(client, global_seed=global_seed)
        start_month = shift_month(target_month, -(MAX_MONTHS_PER_CLIENT - 1))
        for offset in range(MAX_MONTHS_PER_CLIENT):
            month = shift_month(start_month, offset)
            months_before_target = month_distance(month, target_month)
            tenure = max(0, current_tenure - months_before_target)
            flux, q10, encours = _generate_month_values(
                client,
                annee_mois=month,
                anciennete_mois=tenure,
                global_seed=global_seed,
                fake=fake,
            )
            yield (radical, month, flux, q10, encours, tenure)
        return

    previous_month_i = int(previous_month)
    previous_tenure_i = _non_negative_int(previous_tenure)
    distance = month_distance(previous_month_i, target_month)
    if distance <= 0:
        return

    # Si le worker a été arrêté plusieurs mois, on rattrape les mois manquants.
    # On limite le rattrapage aux 15 derniers mois puisque le datamart ne doit
    # jamais conserver une profondeur supérieure.
    first_delta = max(1, distance - MAX_MONTHS_PER_CLIENT + 1)
    for delta in range(first_delta, distance + 1):
        month = shift_month(previous_month_i, delta)
        tenure = previous_tenure_i + delta
        flux, q10, encours = _generate_month_values(
            client,
            annee_mois=month,
            anciennete_mois=tenure,
            global_seed=global_seed,
            fake=fake,
        )
        yield (radical, month, flux, q10, encours, tenure)


def _load_stage(conn, rows: Iterable[tuple[Any, ...]]) -> int:
    count = 0
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE {STAGE_TABLE}")
        with cur.copy(
            f"""
            COPY {STAGE_TABLE} (
                radical_compte,
                annee_mois,
                flux_crediteur_m,
                moyenne_10pc_plus_petits,
                encours_m_moyen,
                anciennete_mois
            ) FROM STDIN
            """
        ) as copy:
            for row in rows:
                copy.write_row(row)
                count += 1
    return count


def _merge_stage_and_prune(conn) -> tuple[int, int]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO {TARGET_TABLE} (
                radical_compte,
                annee_mois,
                flux_crediteur_m,
                moyenne_10pc_plus_petits,
                encours_m_moyen,
                anciennete_mois
            )
            SELECT
                radical_compte,
                annee_mois,
                flux_crediteur_m,
                moyenne_10pc_plus_petits,
                encours_m_moyen,
                anciennete_mois
            FROM {STAGE_TABLE}
            ON CONFLICT (radical_compte, annee_mois) DO NOTHING
            """
        )
        inserted = max(0, int(cur.rowcount or 0))

        cur.execute(
            f"""
            WITH touched AS (
                SELECT DISTINCT radical_compte
                FROM {STAGE_TABLE}
            ), ranked AS (
                SELECT
                    d.radical_compte,
                    d.annee_mois,
                    ROW_NUMBER() OVER (
                        PARTITION BY d.radical_compte
                        ORDER BY d.annee_mois DESC
                    ) AS rn
                FROM {TARGET_TABLE} AS d
                JOIN touched AS t USING (radical_compte)
            )
            DELETE FROM {TARGET_TABLE} AS d
            USING ranked AS r
            WHERE d.radical_compte = r.radical_compte
              AND d.annee_mois = r.annee_mois
              AND r.rn > %s
            """,
            (MAX_MONTHS_PER_CLIENT,),
        )
        deleted = max(0, int(cur.rowcount or 0))
    return inserted, deleted


def ensure_segmentation_datamart_current(
    *,
    annee_mois: Optional[int] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    target_month = parse_yyyymm(annee_mois or current_yyyymm())
    effective_seed = int(seed if seed is not None else os.getenv("SEGMENTATION_FAKE_SEED", DEFAULT_SEED))
    if batch_size < 1:
        raise ValueError("batch_size doit être >= 1")

    conn = get_connection(autocommit=False)
    lock_acquired = False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (SEGMENTATION_DATAMART_ADVISORY_LOCK_KEY,))
            row = cur.fetchone()
            lock_acquired = bool(row and row[0])
        if not lock_acquired:
            raise SegmentationDatamartAlreadyRunningError(
                "Une autre alimentation du datamart segmentation est déjà en cours."
            )

        before = _period_counts(conn, target_month)
        if before["clients"] == before["current_rows"]:
            conn.commit()
            return {
                "ok": True,
                "annee_mois": target_month,
                "clients": before["clients"],
                "rows_before": before["current_rows"],
                "rows_after": before["current_rows"],
                "clients_enriched": 0,
                "rows_inserted": 0,
                "rows_pruned": 0,
                "ready": True,
            }

        _ensure_stage_table(conn)
        conn.commit()
        fake = Faker("fr_FR")
        after_radical: Optional[str] = None
        clients_enriched = 0
        rows_inserted = 0
        rows_pruned = 0

        while True:
            clients = _fetch_missing_client_batch(
                conn,
                annee_mois=target_month,
                after_radical=after_radical,
                limit=batch_size,
            )
            if not clients:
                break

            def generated_rows() -> Iterable[tuple[Any, ...]]:
                for client in clients:
                    yield from _rows_for_client(
                        client,
                        target_month=target_month,
                        global_seed=effective_seed,
                        fake=fake,
                    )

            staged = _load_stage(conn, generated_rows())
            inserted, deleted = _merge_stage_and_prune(conn)
            conn.commit()

            clients_enriched += len(clients)
            rows_inserted += inserted
            rows_pruned += deleted
            after_radical = str(clients[-1]["radical_compte"])
            logger.info(
                "Datamart segmentation %s: clients=%s staged=%s inserted=%s pruned=%s last=%s",
                target_month,
                clients_enriched,
                staged,
                rows_inserted,
                rows_pruned,
                after_radical,
            )

        after = _period_counts(conn, target_month)
        ready = after["clients"] == after["current_rows"]
        if not ready:
            raise RuntimeError(
                "Datamart segmentation encore incomplet après alimentation: "
                f"clients={after['clients']:,}, lignes_mois={after['current_rows']:,}."
            )

        return {
            "ok": True,
            "annee_mois": target_month,
            "clients": after["clients"],
            "rows_before": before["current_rows"],
            "rows_after": after["current_rows"],
            "clients_enriched": clients_enriched,
            "rows_inserted": rows_inserted,
            "rows_pruned": rows_pruned,
            "ready": True,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        if lock_acquired:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)", (SEGMENTATION_DATAMART_ADVISORY_LOCK_KEY,))
                conn.commit()
            except Exception:
                logger.exception("Impossible de libérer le verrou du datamart segmentation.")
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Maintient automatiquement le datamart variables de segmentation à 15 mois."
    )
    parser.add_argument(
        "--month",
        default=str(current_yyyymm()),
        help="Mois cible YYYYMM (défaut : mois courant Africa/Casablanca).",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    result = ensure_segmentation_datamart_current(
        annee_mois=parse_yyyymm(args.month),
        batch_size=args.batch_size,
        seed=args.seed,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
