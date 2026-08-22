from __future__ import annotations

import logging
import os
import random
import zlib
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Sequence

from faker import Faker

from app.best_channel.history import CANONICAL_CHANNELS, age_band, result_quality
from app.domain.canaux import resultats_for_canal

logger = logging.getLogger(__name__)


def _canonical_results(canal: str) -> List[str]:
    source = "Whatsapp information" if canal == "Whatsapp" else canal
    return list(resultats_for_canal(source) or ["Sans résultat"])


def _fake_message(fake: Faker, canal: str) -> str:
    return f"Sollicitation commerciale {canal}. Réf. {fake.bothify(text='??-####').upper()}"


def _action_count(rng: random.Random) -> int:
    """Distribution volontairement réaliste : majorité peu sollicitée.

    Environ 58 % n'ont aucune action supplémentaire, 25 % en ont 1-2,
    12 % en ont 3-4, 4 % en ont 5-7 et 1 % en ont 8-11.
    """
    p = rng.random()
    if p < 0.58:
        return 0
    if p < 0.83:
        return rng.randint(1, 2)
    if p < 0.95:
        return rng.randint(3, 4)
    if p < 0.99:
        return rng.randint(5, 7)
    return rng.randint(8, 11)


def _iter_rows(clients: Sequence[Dict[str, Any]], run_date: date) -> Iterable[tuple]:
    start = run_date - timedelta(days=29)
    campaign = f"FAKE_PRESSURE_{run_date.year}{run_date.month:02d}"

    fake = Faker("fr_FR")
    for client in clients:
        radical = str(client.get("radical_compte") or "").strip()
        if not radical:
            continue
        seed = zlib.crc32(f"pressure|{radical}|{run_date.year}{run_date.month:02d}".encode("utf-8")) & 0xFFFFFFFF
        rng = random.Random(seed)
        action_count = _action_count(rng)
        if action_count <= 0:
            continue

        fake.seed_instance(seed)
        region = str(client.get("Region") or "Inconnue")
        tranche = age_band(client.get("Age"))

        # Les clients les plus sollicités ont davantage de contacts rapprochés,
        # ce qui permet au moteur de pression de tester ses règles de répétition.
        if action_count >= 5:
            recent_days = min(6, max(2, action_count - 1))
            day_offsets = [rng.randint(0, recent_days) for _ in range(action_count)]
        else:
            day_offsets = [rng.randint(0, 29) for _ in range(action_count)]
        day_offsets.sort(reverse=True)

        channels = list(CANONICAL_CHANNELS)
        for order, days_old in enumerate(day_offsets, start=1):
            canal = channels[rng.randrange(len(channels))]
            values = _canonical_results(canal)
            # Majorité d'actions réellement exposées, quelques échecs techniques.
            result = values[rng.randrange(len(values))]
            if rng.random() < 0.72:
                preferred = {
                    "Appel": "Joignable avec succès",
                    "SMS": "Transmis",
                    "Mail": "Transmis",
                    "Whatsapp": "Délivré",
                    "Directeur d'agence": "Aboutit",
                    "Conseiller client": "Aboutit",
                    "Push notification": "Transmis",
                }.get(canal)
                if preferred in values:
                    result = preferred

            observed_day = run_date - timedelta(days=int(days_old))
            observed = datetime.combine(
                observed_day,
                time(hour=rng.randint(8, 20), minute=rng.randint(0, 59)),
                tzinfo=timezone.utc,
            )
            event_key = f"fake:pressure:v1:{radical}:{run_date.year}{run_date.month:02d}:{order}"
            yield (
                "fake", campaign, radical, 1, f"P{order}", order, order - 1,
                canal, _fake_message(fake, canal), result, result_quality(result),
                0, None, tranche, region, observed, None, event_key,
            )


def bootstrap_pressure_fake_interactions(conn, *, run_date: date) -> Dict[str, Any]:
    """Ajoute un jeu fake de sollicitations uniquement tant qu'il n'y a pas de réel.

    Ces lignes restent volontairement non finalisées : elles servent au moteur
    de pression mais ne rentrent pas dans l'entraînement Best Channel.
    """
    month_tag = f"FAKE_PRESSURE_{run_date.year}{run_date.month:02d}"
    window_start = run_date - timedelta(days=29)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS real_recent
            FROM dm_best_channel_interactions
            WHERE source = 'reel'
              AND observed_at >= %s::date
              AND observed_at < (%s::date + INTERVAL '1 day')
            """,
            (window_start, run_date),
        )
        row = cur.fetchone()
        real_recent = int((row.get("real_recent") if isinstance(row, dict) else row[0]) or 0)
        if real_recent > 0:
            # Dès que des actions réelles existent, le bootstrap n'a plus de
            # rôle : on retire ses événements synthétiques afin qu'ils ne
            # contaminent pas les fenêtres de pression suivantes.
            cur.execute("DELETE FROM dm_best_channel_interactions WHERE id_campagne LIKE 'FAKE_PRESSURE_%'")
            removed = int(cur.rowcount or 0)
            conn.commit()
            return {
                "ok": True,
                "bootstrapped": False,
                "reason": "real_interactions_available",
                "real_recent": real_recent,
                "fake_rows_removed": removed,
            }

        # Sur une installation vide, Best Channel doit créer en premier son
        # historique d'apprentissage finalisé. Sans cette garde, les deux
        # bootstraps pourraient se concurrencer au premier démarrage.
        cur.execute("SELECT COUNT(*) AS total FROM dm_best_channel_interactions WHERE finalized_at IS NOT NULL")
        finalized_row = cur.fetchone()
        finalized = int((finalized_row.get("total") if isinstance(finalized_row, dict) else finalized_row[0]) or 0)
        if finalized <= 0:
            return {
                "ok": True,
                "bootstrapped": False,
                "reason": "waiting_for_best_channel_history",
                "finalized_rows": 0,
            }

        cur.execute("SELECT COUNT(*) AS total FROM dm_best_channel_interactions WHERE id_campagne = %s", (month_tag,))
        row = cur.fetchone()
        existing = int((row.get("total") if isinstance(row, dict) else row[0]) or 0)
        cur.execute(
            "SELECT COUNT(*) AS total FROM dm_commercial_pressure_scores WHERE annee_mois = %s",
            (run_date.year * 100 + run_date.month,),
        )
        score_row = cur.fetchone()
        current_scores = int((score_row.get("total") if isinstance(score_row, dict) else score_row[0]) or 0)
        if existing > 0 and current_scores > 0:
            return {
                "ok": True,
                "bootstrapped": False,
                "reason": "already_present",
                "rows": existing,
                "scores_current_month": current_scores,
            }

        # Si un crash est survenu pendant le bootstrap, on reparcourt les
        # clients : ON CONFLICT(event_key) complète uniquement les lignes
        # manquantes sans dupliquer celles déjà insérées.
        cur.execute(
            """
            SELECT radical_compte, "Age", "Region", "STATUT_CLIENT"
            FROM clients
            WHERE "STATUT_CLIENT" IN ('Actif', 'Inactif')
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
            tranche_age, region, observed_at, finalized_at, event_key, updated_at
        ) VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()
        ) ON CONFLICT (event_key) DO NOTHING
    """
    batch_size = max(500, int(os.getenv("COMMERCIAL_PRESSURE_FAKE_BATCH_SIZE", "5000") or "5000"))
    inserted = 0
    batch: List[tuple] = []
    with conn.cursor() as cur:
        for item in _iter_rows(clients, run_date):
            batch.append(item)
            if len(batch) >= batch_size:
                cur.executemany(insert_sql, batch)
                inserted += max(0, int(cur.rowcount or 0))
                conn.commit()
                batch.clear()
        if batch:
            cur.executemany(insert_sql, batch)
            inserted += max(0, int(cur.rowcount or 0))
            conn.commit()

    logger.info("Bootstrap pression commerciale terminé: rows_inserted=%s clients=%s", inserted, len(clients))
    return {"ok": True, "bootstrapped": True, "rows_inserted": inserted, "eligible_clients": len(clients)}
