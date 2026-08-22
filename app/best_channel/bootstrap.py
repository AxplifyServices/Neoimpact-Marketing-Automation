from __future__ import annotations

import logging
import math
import os
import random
import zlib
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Sequence

from faker import Faker

from app.best_channel.history import CANONICAL_CHANNELS, age_band, result_quality
from app.domain.canaux import resultats_for_canal

logger = logging.getLogger(__name__)

FAKE_CAMPAIGNS = [f"FAKE_BEST_CHANNEL_{i:02d}" for i in range(1, 9)]


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _add_months(value: date, delta: int) -> date:
    total = value.year * 12 + (value.month - 1) + int(delta)
    return date(total // 12, total % 12 + 1, 1)


def _canonical_results(canal: str) -> List[str]:
    if canal == "Whatsapp":
        raw = resultats_for_canal("Whatsapp information")
    else:
        raw = resultats_for_canal(canal)
    return list(raw or ["Sans résultat"])


def _good_result_index(canal: str, values: Sequence[str]) -> int:
    preferred = {
        "Appel": ["Joignable avec succès"],
        "SMS": ["Transmis"],
        "Mail": ["Transmis"],
        "Whatsapp": ["Lu", "Délivré"],
        "Directeur d'agence": ["Aboutit"],
        "Conseiller client": ["Aboutit"],
        "Push notification": ["Lu", "Transmis"],
    }
    for candidate in preferred.get(canal, []):
        for index, value in enumerate(values):
            if str(value).strip().lower() == candidate.lower():
                return index
    return 0


def _client_preference(age_group: str, region: str) -> str:
    """Préférence latente déterministe utilisée uniquement pour rendre le fake data apprenable."""
    key = zlib.crc32(f"{age_group}|{region}".encode("utf-8")) % 100
    if age_group in {"0-17", "18-24", "25-34"}:
        ordered = ["Push notification", "Whatsapp", "SMS", "Mail", "Appel", "Conseiller client", "Directeur d'agence"]
    elif age_group in {"50-59", "60+"}:
        ordered = ["Appel", "Conseiller client", "Directeur d'agence", "SMS", "Mail", "Whatsapp", "Push notification"]
    else:
        ordered = ["Mail", "Whatsapp", "Appel", "SMS", "Push notification", "Conseiller client", "Directeur d'agence"]
    return ordered[key % len(ordered)]


def _message(fake: Faker, canal: str) -> str:
    templates = {
        "Appel": "Appel commercial concernant une offre adaptée au profil client.",
        "SMS": "Découvrez votre nouvelle offre personnalisée dans votre espace client.",
        "Mail": "Une offre sélectionnée selon votre profil est disponible.",
        "Whatsapp": "Message WhatsApp personnalisé concernant une offre bancaire.",
        "Directeur d'agence": "Prise de contact du directeur d'agence pour accompagner le client.",
        "Conseiller client": "Prise de contact du conseiller client pour présenter une offre.",
        "Push notification": "Notification mobile concernant une offre personnalisée.",
    }
    base = templates.get(canal, "Action commerciale personnalisée.")
    # Faker intervient dans le contenu sans rendre le bootstrap inutilement coûteux.
    return f"{base} Réf. {fake.bothify(text='??-####').upper()}"


def _iter_fake_rows(clients: Sequence[Dict[str, Any]], run_date: date) -> Iterable[tuple]:
    end_month = _month_start(run_date)
    start_month = _add_months(end_month, -11)

    for client in clients:
        radical = str(client.get("radical_compte") or "").strip()
        if not radical:
            continue
        region = str(client.get("Region") or "Inconnue")
        tranche = age_band(client.get("Age"))
        seed = zlib.crc32(radical.encode("utf-8")) & 0xFFFFFFFF
        rng = random.Random(seed)
        fake = Faker("fr_FR")
        fake.seed_instance(seed)

        sequences = 1 + (1 if rng.random() < 0.22 else 0)
        preferred = _client_preference(tranche, region)

        for seq_index in range(1, sequences + 1):
            month_offset = rng.randint(0, 11)
            month = _add_months(start_month, month_offset)
            days_in_month = max(1, (_add_months(month, 1) - month).days)
            event_day = month + timedelta(days=rng.randint(0, days_in_month - 1))
            campaign = FAKE_CAMPAIGNS[rng.randrange(len(FAKE_CAMPAIGNS))]
            block_count = rng.randint(2, 4)
            channels = rng.sample(CANONICAL_CHANNELS, k=min(block_count, len(CANONICAL_CHANNELS)))
            if preferred not in channels and rng.random() < 0.55:
                channels[-1] = preferred

            staged = []
            sequence_strength = 0.0
            for block_order, canal in enumerate(channels, start=1):
                values = _canonical_results(canal)
                good_idx = _good_result_index(canal, values)
                good_probability = 0.58 + (0.10 if canal == preferred else 0.0)
                if rng.random() < good_probability:
                    result = values[good_idx]
                else:
                    alternatives = [v for i, v in enumerate(values) if i != good_idx] or values
                    result = alternatives[rng.randrange(len(alternatives))]
                quality = result_quality(result)
                sequence_strength = max(sequence_strength, quality + (0.18 if canal == preferred else 0.0))
                observed = datetime.combine(event_day, time(hour=rng.randint(8, 19), minute=rng.randint(0, 59)), tzinfo=timezone.utc)
                block_id = f"B{block_order}"
                event_key = f"fake:{campaign}:{radical}:{seq_index}:{block_order}:{int(observed.timestamp())}"
                staged.append((
                    "fake", campaign, radical, seq_index, block_id, block_order, block_order - 1,
                    canal, _message(fake, canal), result, quality,
                    tranche, region, observed, event_key,
                ))

            # Taux de conversion volontairement bas (~4-8 %), légèrement amélioré par un bon canal/résultat.
            probability = 0.025 + (0.022 if preferred in channels else 0.0) + max(0.0, sequence_strength - 0.75) * 0.07
            probability = min(0.085, max(0.02, probability))
            objective = 1 if rng.random() < probability else 0
            objective_id = f"OBJ{seq_index}"
            finalized = max(row[13] for row in staged) + timedelta(minutes=3)
            for row in staged:
                yield (*row[:11], objective, objective_id, *row[11:14], finalized, row[14])


def bootstrap_fake_interactions(conn, *, run_date: date) -> Dict[str, Any]:
    """Crée un historique fake seulement si aucune donnée d'apprentissage n'existe."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM dm_best_channel_interactions")
        count_row = cur.fetchone()
        if isinstance(count_row, dict):
            existing = int(count_row.get("total") or 0)
        else:
            existing = int((count_row or [0])[0] or 0)
        if existing > 0:
            return {"ok": True, "bootstrapped": False, "rows": existing}

        cur.execute(
            """
            SELECT radical_compte, "Age", "Region", "STATUT_CLIENT"
            FROM clients
            WHERE "STATUT_CLIENT" IN ('Actif', 'Inactif')
              AND MOD((hashtextextended(radical_compte, 0) & 2147483647), 100) < 28
            ORDER BY radical_compte
            """
        )
        clients = [dict(row) if isinstance(row, dict) else {
            "radical_compte": row[0], "Age": row[1], "Region": row[2], "STATUT_CLIENT": row[3]
        } for row in cur.fetchall()]

    insert_sql = """
        INSERT INTO dm_best_channel_interactions (
            source, id_campagne, radical_compte, sequence_no, block_id,
            block_order, action_execution_seq, canal, message, resultat_bloc,
            qualite_resultat, objectif_valide, objectif_id_action,
            tranche_age, region, observed_at, finalized_at, event_key,
            updated_at
        ) VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()
        ) ON CONFLICT (event_key) DO NOTHING
    """
    batch_size = max(500, int(os.getenv("BEST_CHANNEL_FAKE_BATCH_SIZE", "5000") or "5000"))
    rows_inserted = 0
    batch: List[tuple] = []
    with conn.cursor() as cur:
        for row in _iter_fake_rows(clients, run_date):
            batch.append(row)
            if len(batch) >= batch_size:
                cur.executemany(insert_sql, batch)
                rows_inserted += max(0, int(cur.rowcount or 0))
                conn.commit()
                batch.clear()
        if batch:
            cur.executemany(insert_sql, batch)
            rows_inserted += max(0, int(cur.rowcount or 0))
            conn.commit()

    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE objectif_valide=1) AS positives
            FROM dm_best_channel_interactions
        """)
        summary = cur.fetchone()
        if isinstance(summary, dict):
            total = int(summary.get("total") or 0)
            positives = int(summary.get("positives") or 0)
        else:
            total, positives = summary
    logger.info("Bootstrap Best Channel terminé: rows=%s positives=%s", total, positives)
    return {
        "ok": True,
        "bootstrapped": True,
        "rows_inserted": int(rows_inserted),
        "rows": int(total or 0),
        "positive_rows": int(positives or 0),
    }
