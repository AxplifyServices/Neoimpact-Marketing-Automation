from __future__ import annotations

import argparse
import hashlib
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from faker import Faker


DEFAULT_SEED = 20260821
DEFAULT_MONTHS = 15
DEFAULT_BATCH_SIZE = 5_000
TIMEZONE = "Africa/Casablanca"

TARGET_TABLE = "dm_segmentation_variables"
STAGE_TABLE = "_dm_segmentation_variables_stage"

COLUMNS = (
    "radical_compte",
    "annee_mois",
    "flux_crediteur_m",
    "moyenne_10pc_plus_petits",
    "encours_m_moyen",
    "anciennete_mois",
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_environment() -> None:
    load_dotenv(project_root() / ".env", override=False)


def database_url() -> str:
    value = str(os.getenv("DATABASE_URL") or "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL est absent.")
    return value


def stable_seed(global_seed: int, radical_compte: str) -> int:
    digest = hashlib.blake2b(
        f"{global_seed}|{radical_compte}".encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big", signed=False)


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


def text_yes(value: Any) -> bool:
    return str(value or "").strip().lower() in {"oui", "yes", "1", "true"}


def as_non_negative_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return max(0.0, parsed)


def as_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, parsed)


def build_history_rows(
    client: dict[str, Any],
    *,
    end_month: int,
    months: int,
    global_seed: int,
    fake: Faker,
) -> Iterable[tuple[Any, ...]]:
    radical = str(client["radical_compte"])

    # On resème Faker par client : le résultat est reproductible et ne dépend
    # pas du nombre de clients traités avant lui.
    fake.seed_instance(stable_seed(global_seed, radical))
    rng = fake.random

    anciennete_annees = as_non_negative_int(client.get("Anciennete"))
    # La table clients ne stocke aujourd'hui que l'ancienneté entière en années.
    # On enrichit donc le datamart avec un mois résiduel déterministe sans toucher
    # à clients. Les clients Anciennete=0 couvrent naturellement 0..11 mois.
    anciennete_courante_mois = anciennete_annees * 12 + rng.randint(0, 11)

    montant_revenu = as_non_negative_float(client.get("montant_revenu"))
    solde_moyen = as_non_negative_float(client.get("solde_moyen_depots"))
    bp = text_yes(client.get("BP"))
    revenu_domicilie = text_yes(client.get("revenu_domicilie"))

    if montant_revenu < 1.0:
        montant_revenu = round(rng.triangular(1_500.0, 35_000.0, 6_500.0), 2)

    # Profil latent uniquement utilisé pour produire les données de test.
    # Il n'est jamais écrit en base : le moteur devra le redétecter à partir
    # de la fréquence/régularité des flux, comme dans le notebook fourni.
    salarie_probability = 0.88 if revenu_domicilie else 0.46
    if montant_revenu < 2_000:
        salarie_probability *= 0.55
    latent_salarie = rng.random() < salarie_probability

    base_avoirs = solde_moyen
    if base_avoirs < 1.0:
        base_avoirs = montant_revenu * rng.uniform(0.7, 7.0)
    if bp:
        base_avoirs = max(base_avoirs, montant_revenu * rng.uniform(18.0, 55.0))

    start_month = shift_month(end_month, -(months - 1))

    for offset in range(months):
        annee_mois = shift_month(start_month, offset)
        months_before_current = months - 1 - offset
        anciennete_mois = max(0, anciennete_courante_mois - months_before_current)

        # Les mois antérieurs à l'entrée en relation restent présents afin de
        # conserver exactement 15 lignes par client, mais avec des valeurs à 0.
        relationship_started = anciennete_courante_mois >= months_before_current
        if not relationship_started:
            yield (radical, annee_mois, 0.0, 0.0, 0.0, 0)
            continue

        trend = 1.0 + (offset - (months - 1)) * rng.uniform(-0.006, 0.012)
        trend = max(0.70, trend)

        if latent_salarie:
            if rng.random() < 0.93:
                flux = montant_revenu * trend * rng.normalvariate(1.0, 0.065)
                if rng.random() < 0.08:
                    flux *= rng.uniform(1.08, 1.35)
            else:
                flux = rng.uniform(0.0, min(1_900.0, montant_revenu * 0.30))
        else:
            if rng.random() < 0.28:
                flux = rng.uniform(0.0, min(1_900.0, montant_revenu * 0.40))
            else:
                # Distribution volontairement irrégulière : la classification
                # salarié/non-salarié doit être retrouvée par le code historique.
                flux = montant_revenu * trend * rng.lognormvariate(-0.12, 0.78)

        flux = round(max(0.0, flux), 2)

        avoir_month = base_avoirs * trend * rng.lognormvariate(0.0, 0.13 if latent_salarie else 0.28)
        avoir_month = max(0.0, avoir_month)

        # Input mensuel attendu par le notebook pour les non-salariés.
        encours_m_moyen = round(avoir_month, 2)

        # Approximation du quantile bas des soldes journaliers, input attendu
        # par le notebook pour les salariés. On ne simule pas ici un ledger
        # journalier : le but du MVP est d'enrichir le datamart mensuel existant.
        if latent_salarie:
            q10_factor = rng.uniform(0.32, 0.72)
        else:
            q10_factor = rng.uniform(0.48, 0.92)
        moyenne_10pc_plus_petits = round(avoir_month * q10_factor, 2)

        yield (
            radical,
            annee_mois,
            flux,
            moyenne_10pc_plus_petits,
            encours_m_moyen,
            anciennete_mois,
        )


def ensure_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema='public'
                  AND table_name=%s
            )
            """,
            (TARGET_TABLE,),
        )
        row = cur.fetchone()
        if not row or not bool(row[0]):
            raise RuntimeError(
                f"La table {TARGET_TABLE!r} est absente. "
                "Applique d'abord database/init/015_segmentation_datamarts.sql."
            )


def ensure_stage_table(conn: psycopg.Connection) -> None:
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


def fetch_client_batch(
    conn: psycopg.Connection,
    *,
    after_radical: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    # Keyset pagination. On sépare explicitement le premier batch des suivants
    # pour éviter le paramètre NULL non typé de PostgreSQL et conserver une
    # requête simple pouvant utiliser l'index/PK sur clients.radical_compte.
    base_query = """
        SELECT
            radical_compte,
            "Anciennete",
            montant_revenu,
            solde_moyen_depots,
            revenu_domicilie,
            "BP"
        FROM clients
    """

    with conn.cursor(row_factory=dict_row) as cur:
        if after_radical is None:
            cur.execute(
                base_query
                + """
                    ORDER BY radical_compte
                    LIMIT %s
                """,
                (limit,),
            )
        else:
            cur.execute(
                base_query
                + """
                    WHERE radical_compte > %s
                    ORDER BY radical_compte
                    LIMIT %s
                """,
                (after_radical, limit),
            )

        return [dict(row) for row in cur.fetchall()]


def load_stage(
    conn: psycopg.Connection,
    rows: Iterable[tuple[Any, ...]],
) -> int:
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


def merge_stage_and_prune(conn: psycopg.Connection) -> None:
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
            ON CONFLICT (radical_compte, annee_mois)
            DO UPDATE SET
                flux_crediteur_m = EXCLUDED.flux_crediteur_m,
                moyenne_10pc_plus_petits = EXCLUDED.moyenne_10pc_plus_petits,
                encours_m_moyen = EXCLUDED.encours_m_moyen,
                anciennete_mois = EXCLUDED.anciennete_mois,
                updated_at = NOW()
            """
        )

        # Invariant métier : jamais plus de 15 mois par client.
        # Le nettoyage est effectué dans la même transaction que l'upsert :
        # les autres sessions ne voient donc jamais un état > 15 lignes.
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
                FROM {TARGET_TABLE} d
                JOIN touched t USING (radical_compte)
            )
            DELETE FROM {TARGET_TABLE} d
            USING ranked r
            WHERE d.radical_compte = r.radical_compte
              AND d.annee_mois = r.annee_mois
              AND r.rn > %s
            """,
            (DEFAULT_MONTHS,),
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Enrichit les clients existants avec 15 mois de variables de "
            "segmentation. Aucun client n'est créé."
        )
    )
    parser.add_argument(
        "--end-month",
        default=str(current_yyyymm()),
        help="Dernier mois à générer au format YYYYMM (défaut: mois courant).",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=DEFAULT_MONTHS,
        help="Profondeur à générer. Le besoin MVP impose 15 mois.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Seed Faker déterministe.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Nombre de clients traités par transaction.",
    )
    args = parser.parse_args()

    if args.months != DEFAULT_MONTHS:
        raise ValueError("Le datamart segmentation doit conserver exactement 15 mois.")
    if args.batch_size < 1:
        raise ValueError("--batch-size doit être >= 1.")

    end_month = parse_yyyymm(args.end_month)

    load_environment()
    fake = Faker("fr_FR")

    processed_clients = 0
    written_rows = 0
    after_radical: str | None = None

    with psycopg.connect(database_url()) as conn:
        ensure_schema(conn)
        ensure_stage_table(conn)
        conn.commit()

        while True:
            clients = fetch_client_batch(
                conn,
                after_radical=after_radical,
                limit=args.batch_size,
            )
            if not clients:
                break

            def rows_for_batch() -> Iterable[tuple[Any, ...]]:
                for client in clients:
                    yield from build_history_rows(
                        client,
                        end_month=end_month,
                        months=args.months,
                        global_seed=args.seed,
                        fake=fake,
                    )

            count = load_stage(conn, rows_for_batch())
            merge_stage_and_prune(conn)
            conn.commit()

            processed_clients += len(clients)
            written_rows += count
            after_radical = str(clients[-1]["radical_compte"])

            print(
                f"[segmentation-seed] clients={processed_clients:,} "
                f"rows={written_rows:,} last={after_radical}",
                flush=True,
            )

    print(
        f"[OK] {processed_clients:,} clients existants enrichis, "
        f"{written_rows:,} lignes générées/upsertées jusqu'à {end_month}.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
