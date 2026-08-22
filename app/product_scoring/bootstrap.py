from __future__ import annotations

import logging
import math
import os
import random
import zlib
from datetime import date
from typing import Any, Dict, Iterable, Sequence

from app.product_scoring.constants import CARD_PRODUCTS, card_rank, yes
from app.storage.postgres_db import connection

logger = logging.getLogger(__name__)


def _month_shift(day: date, offset: int) -> tuple[int, date]:
    idx = day.year * 12 + (day.month - 1) + offset
    year, month0 = divmod(idx, 12)
    month = month0 + 1
    return year * 100 + month, date(year, month, 1)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-12.0, min(12.0, x))))


def _clip_delta(value: float) -> float:
    return max(-1.0, min(3.0, value))


def _target(rng: random.Random, logit: float) -> int:
    return 1 if rng.random() < _sigmoid(logit) else 0


def _fake_rows(clients: Sequence[Dict[str, Any]], run_date: date) -> Iterable[tuple]:
    # 12 mois terminés, jamais le mois courant : le mois courant est toujours
    # une vraie photo du datamart clients.
    months = [_month_shift(run_date, offset) for offset in range(-12, 0)]
    for client in clients:
        radical = str(client.get("radical_compte") or "").strip()
        if not radical:
            continue
        base_seed = zlib.crc32(f"product|{radical}".encode("utf-8")) & 0xFFFFFFFF
        base_income = float(client.get("montant_revenu") or 0.0)
        base_deposits = float(client.get("solde_moyen_depots") or 0.0)
        base_txn = float(client.get("nb_transaction") or 0.0)
        base_vol = float(client.get("vol_transaction") or 0.0)
        base_conso = float(client.get("encours_conso") or 0.0)
        base_immo = float(client.get("encours_immo") or 0.0)
        current_rank = card_rank(client.get("Carte_Actuelle"))
        current_epargne = 1 if yes(client.get("Epargne")) else 0

        # Le datamart MVP actuel contient des encours Faker qui rendent presque
        # tous les clients artificiellement "active" sur les crédits. Pour
        # entraîner réellement les trois modèles demandés, l'historique fake
        # reconstruit des états d'équipement plausibles et suffisamment variés.
        state_rng = random.Random(base_seed ^ 0xA53C91)
        conso_roll = state_rng.random()
        immo_roll = state_rng.random()
        conso_state = "never" if conso_roll < 0.58 else ("finished" if conso_roll < 0.78 else "active")
        immo_state = "never" if immo_roll < 0.70 else ("finished" if immo_roll < 0.86 else "active")
        synthetic_rank = current_rank
        synthetic_epargne = current_epargne
        age = int(client.get("Age") or 0)
        digital = 1 if yes(client.get("App_instaled")) else 0
        connected = 1 if yes(client.get("Premiere_connex")) else 0
        segment = str(client.get("Segment_actuel") or "non_segmente")
        segment_bonus = {"Mass Market": -0.2, "Medium": 0.1, "Haut de gamme": 0.45, "Premium": 0.75, "Banque privée": 1.0}.get(segment, 0.0)

        prev_txn = max(0.0, base_txn * 0.75)
        prev_deposits = max(0.0, base_deposits * 0.8)
        prev_income = max(0.0, base_income * 0.9)
        prev_conso = max(0.0, base_conso * 0.8)
        prev_immo = max(0.0, base_immo * 0.9)

        for idx, (month, observed) in enumerate(months):
            rng = random.Random(base_seed ^ month)
            season = 0.90 + 0.20 * rng.random()
            progress = 0.82 + 0.18 * ((idx + 1) / len(months))
            txn = max(0.0, base_txn * season * progress + rng.uniform(-3, 3))
            vol = max(0.0, base_vol * season * progress * rng.uniform(0.85, 1.15))
            deposits = max(0.0, base_deposits * progress * rng.uniform(0.75, 1.25))
            income = max(0.0, base_income * rng.uniform(0.90, 1.10))
            if conso_state == "active":
                conso = max(750.0, (base_conso if base_conso > 500 else rng.uniform(5_000, 180_000)) * rng.uniform(0.78, 1.08))
            elif conso_state == "finished":
                conso = rng.uniform(0.0, 350.0)
            else:
                conso = 0.0
            if immo_state == "active":
                immo = max(5_000.0, (base_immo if base_immo > 1_000 else rng.uniform(80_000, 750_000)) * rng.uniform(0.94, 1.03))
            elif immo_state == "finished":
                immo = rng.uniform(0.0, 750.0)
            else:
                immo = 0.0
            ecom_n = max(0.0, float(client.get("nb_transaction_ecom") or 0.0) * rng.uniform(0.7, 1.3))
            ecom_v = max(0.0, float(client.get("vol_transaction_ecom") or 0.0) * rng.uniform(0.7, 1.3))
            withdrawal_n = max(0.0, float(client.get("nb_retrait_gab") or 0.0) * rng.uniform(0.7, 1.3))
            withdrawal_v = max(0.0, float(client.get("vol_retrait_gab") or 0.0) * rng.uniform(0.7, 1.3))
            vir_n = max(0.0, float(client.get("nb_virement") or 0.0) * rng.uniform(0.7, 1.3))
            vir_v = max(0.0, float(client.get("vol_virement") or 0.0) * rng.uniform(0.7, 1.3))
            global_outstanding = max(conso + immo, float(client.get("encours_global") or 0.0) * rng.uniform(0.8, 1.1))

            d_txn = _clip_delta((txn - prev_txn) / max(abs(prev_txn), 1.0))
            d_dep = _clip_delta((deposits - prev_deposits) / max(abs(prev_deposits), 1.0))
            d_inc = _clip_delta((income - prev_income) / max(abs(prev_income), 1.0))
            d_conso = _clip_delta((conso - prev_conso) / max(abs(prev_conso), 1.0))
            d_immo = _clip_delta((immo - prev_immo) / max(abs(prev_immo), 1.0))

            # Historique de campagnes synthétique très léger : il fournit la
            # structure d'apprentissage, les vraies campagnes prendront ensuite
            # naturellement le relais dans les mois réels.
            contacts_card = rng.randint(0, 2) if rng.random() < 0.18 else 0
            contacts_conso = rng.randint(0, 2) if rng.random() < 0.10 else 0
            contacts_immo = 1 if rng.random() < 0.05 else 0
            contacts_epargne = rng.randint(0, 2) if rng.random() < 0.12 else 0
            conv_card = 1 if contacts_card and rng.random() < 0.08 else 0
            conv_conso = 1 if contacts_conso and rng.random() < 0.06 else 0
            conv_immo = 1 if contacts_immo and rng.random() < 0.035 else 0
            conv_epargne = 1 if contacts_epargne and rng.random() < 0.07 else 0

            income_k = math.log1p(income) / 10.0
            deposits_k = math.log1p(deposits) / 11.0
            usage = min(2.0, txn / 35.0) + min(1.5, ecom_n / 15.0)
            digital_bonus = 0.35 * digital + 0.25 * connected
            age_card = 0.25 if 20 <= age <= 55 else -0.15
            age_conso = 0.25 if 23 <= age <= 60 else -0.25
            age_immo = 0.40 if 27 <= age <= 52 else -0.40

            # Les quatre cartes reprennent le principe du notebook : un modèle
            # binaire indépendant par carte. Les cibles positives restent rares.
            target_silver = None if synthetic_rank >= 1 else _target(rng, -4.6 + 0.60*usage + 0.35*income_k + digital_bonus + age_card + 0.20*contacts_card + 0.35*conv_card)
            target_titanium = None if synthetic_rank >= 2 else _target(rng, -5.0 + 0.45*usage + 0.55*income_k + 0.25*deposits_k + digital_bonus + segment_bonus + 0.20*contacts_card + 0.40*conv_card)
            target_platinium = None if synthetic_rank >= 3 else _target(rng, -5.6 + 0.30*usage + 0.70*income_k + 0.55*deposits_k + 0.55*segment_bonus + 0.15*contacts_card + 0.45*conv_card)
            target_infinite = None if synthetic_rank >= 4 else _target(rng, -6.4 + 0.15*usage + 0.85*income_k + 0.80*deposits_k + 0.75*segment_bonus + 0.10*contacts_card + 0.50*conv_card)

            target_epargne = None if synthetic_epargne else _target(rng, -4.5 + 0.70*deposits_k + 0.50*income_k + 0.20*usage + 0.25*d_dep + 0.20*contacts_epargne + 0.55*conv_epargne)

            # Même architecture crédit pour Conso et Immo, avec trois modèles
            # distincts selon l'état d'équipement.
            conso_base = {"never": -4.5, "finished": -4.0, "active": -5.0}[conso_state]
            immo_base = {"never": -5.5, "finished": -5.0, "active": -7.0}[immo_state]
            target_conso = _target(rng, conso_base + 0.65*income_k + 0.35*usage + 0.30*d_txn + age_conso + 0.20*contacts_conso + 0.55*conv_conso - 0.20*math.log1p(conso)/10.0)
            target_immo = _target(rng, immo_base + 0.75*income_k + 0.70*deposits_k + 0.30*d_dep + age_immo + 0.15*contacts_immo + 0.60*conv_immo - 0.35*math.log1p(immo)/10.0)

            yield (
                radical, month, observed, 'fake_mvp',
                client.get("STATUT_CLIENT"), age, client.get("Region"), segment, client.get("Qualite"),
                txn, vol, withdrawal_n, withdrawal_v, ecom_n, ecom_v, vir_n, vir_v,
                deposits, global_outstanding, conso, immo, income, digital, connected,
                (CARD_PRODUCTS[synthetic_rank - 1] if 1 <= synthetic_rank <= 4 else "Aucune"), synthetic_rank, synthetic_epargne, conso_state, immo_state,
                d_txn, d_dep, d_inc, d_conso, d_immo,
                contacts_card, conv_card, contacts_conso, conv_conso, contacts_immo, conv_immo, contacts_epargne, conv_epargne,
                target_silver, target_titanium, target_platinium, target_infinite,
                target_conso, target_immo, target_epargne,
            )
            # Le target représente l'équipement du mois suivant. On fait
            # évoluer l'état synthétique après avoir écrit la ligne du mois,
            # afin que l'historique reste temporellement cohérent.
            acquired_ranks = [
                rank for rank, target in ((1, target_silver), (2, target_titanium), (3, target_platinium), (4, target_infinite))
                if target == 1
            ]
            if acquired_ranks:
                synthetic_rank = max(synthetic_rank, max(acquired_ranks))
            if target_epargne == 1:
                synthetic_epargne = 1
            if target_conso == 1:
                conso_state = "active"
            elif conso_state == "active" and rng.random() < 0.035:
                conso_state = "finished"
            if target_immo == 1:
                immo_state = "active"
            elif immo_state == "active" and rng.random() < 0.015:
                immo_state = "finished"

            prev_txn, prev_deposits, prev_income, prev_conso, prev_immo = txn, deposits, income, conso, immo


def ensure_fake_training_history(run_date: date) -> Dict[str, Any]:
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM dm_product_training_monthly WHERE source='fake_mvp'")
            existing = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute('SELECT COUNT(*) AS n FROM clients WHERE "STATUT_CLIENT" IN (\'Actif\',\'Inactif\')')
            eligible_clients = int((cur.fetchone() or {}).get("n") or 0)
            requested = max(10000, int(os.getenv("PRODUCT_SCORING_FAKE_CLIENTS", "80000") or "80000"))
            sample_size = min(requested, eligible_clients)
            expected_rows = sample_size * 12
            if expected_rows > 0 and existing >= expected_rows:
                return {"bootstrapped": False, "rows": existing, "clients": sample_size}
            cur.execute(
                """
                SELECT radical_compte, "STATUT_CLIENT", "Age", "Region", "Segment_actuel", "Qualite",
                       nb_transaction, vol_transaction, nb_retrait_gab, vol_retrait_gab,
                       nb_transaction_ecom, vol_transaction_ecom, nb_virement, vol_virement,
                       solde_moyen_depots, encours_global, encours_conso, encours_immo,
                       montant_revenu, "App_instaled", "Premiere_connex", "Carte_Actuelle", "Epargne",
                       credit_conso, credit_immo
                FROM clients
                WHERE "STATUT_CLIENT" IN ('Actif','Inactif')
                ORDER BY md5(radical_compte)
                LIMIT %s
                """,
                (sample_size,),
            )
            clients = [dict(row) for row in cur.fetchall()]

    insert_sql = """
        INSERT INTO dm_product_training_monthly (
            radical_compte, annee_mois, observed_on, source,
            statut_client, age, region, segment, qualite,
            nb_transaction, vol_transaction, nb_retrait_gab, vol_retrait_gab,
            nb_transaction_ecom, vol_transaction_ecom, nb_virement, vol_virement,
            solde_moyen_depots, encours_global, encours_conso, encours_immo, montant_revenu,
            app_installed, premiere_connex, carte_actuelle, card_rank, epargne_active,
            credit_conso_state, credit_immo_state,
            delta_transactions, delta_depots, delta_revenu, delta_encours_conso, delta_encours_immo,
            feedback_carte_contacts_12m, feedback_carte_conversions_12m,
            feedback_conso_contacts_12m, feedback_conso_conversions_12m,
            feedback_immo_contacts_12m, feedback_immo_conversions_12m,
            feedback_epargne_contacts_12m, feedback_epargne_conversions_12m,
            target_card_silver, target_card_titanium, target_card_platinium, target_card_infinite,
            target_conso, target_immo, target_epargne
        ) VALUES (""" + ",".join(["%s"] * 49) + ") ON CONFLICT (radical_compte, annee_mois) DO NOTHING"

    inserted = 0
    batch_size = max(500, int(os.getenv("PRODUCT_SCORING_FAKE_BATCH_SIZE", "5000") or "5000"))
    batch: list[tuple] = []
    with connection() as conn:
        with conn.cursor() as cur:
            for row in _fake_rows(clients, run_date):
                batch.append(row)
                if len(batch) >= batch_size:
                    cur.executemany(insert_sql, batch)
                    inserted += len(batch)
                    batch.clear()
                    conn.commit()
            if batch:
                cur.executemany(insert_sql, batch)
                inserted += len(batch)
    logger.info("Bootstrap appétences produits terminé: clients=%s rows=%s", len(clients), inserted)
    return {"bootstrapped": True, "clients": len(clients), "rows_inserted": inserted}
