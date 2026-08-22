from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict

from app.product_scoring.constants import card_rank, credit_state, yes
from app.storage.postgres_db import connection

logger = logging.getLogger(__name__)


def month_key(day: date) -> int:
    return day.year * 100 + day.month


def previous_month_key(day: date) -> int:
    if day.month == 1:
        return (day.year - 1) * 100 + 12
    return day.year * 100 + day.month - 1


def _snapshot_rows(run_date: date) -> int:
    month = month_key(run_date)
    prev_month = previous_month_key(run_date)
    with connection() as conn:
        with conn.cursor() as cur:
            # Le feedback est agrégé avant le mois de scoring afin d'éviter
            # toute fuite de données issue de la campagne en cours.
            cur.execute(
                """
                WITH feedback AS (
                    SELECT
                        radical_compte,
                        COUNT(*) FILTER (WHERE product_code='card' AND was_contacted) AS card_contacts,
                        COUNT(*) FILTER (WHERE product_code='card' AND was_contacted AND objective_achieved=1) AS card_conversions,
                        COUNT(*) FILTER (WHERE product_code='conso' AND was_contacted) AS conso_contacts,
                        COUNT(*) FILTER (WHERE product_code='conso' AND was_contacted AND objective_achieved=1) AS conso_conversions,
                        COUNT(*) FILTER (WHERE product_code='immo' AND was_contacted) AS immo_contacts,
                        COUNT(*) FILTER (WHERE product_code='immo' AND was_contacted AND objective_achieved=1) AS immo_conversions,
                        COUNT(*) FILTER (WHERE product_code='epargne' AND was_contacted) AS epargne_contacts,
                        COUNT(*) FILTER (WHERE product_code='epargne' AND was_contacted AND objective_achieved=1) AS epargne_conversions
                    FROM dm_product_campaign_feedback
                    WHERE campaign_assigned_at >= %s::date - INTERVAL '12 months'
                      AND campaign_assigned_at < %s::date
                    GROUP BY radical_compte
                )
                INSERT INTO dm_product_training_monthly (
                    radical_compte, annee_mois, observed_on, source,
                    statut_client, age, region, segment, qualite,
                    nb_transaction, vol_transaction, nb_retrait_gab, vol_retrait_gab,
                    nb_transaction_ecom, vol_transaction_ecom, nb_virement, vol_virement,
                    solde_moyen_depots, encours_global, encours_conso, encours_immo,
                    montant_revenu, app_installed, premiere_connex,
                    carte_actuelle, card_rank, epargne_active,
                    credit_conso_state, credit_immo_state,
                    delta_transactions, delta_depots, delta_revenu,
                    delta_encours_conso, delta_encours_immo,
                    feedback_carte_contacts_12m, feedback_carte_conversions_12m,
                    feedback_conso_contacts_12m, feedback_conso_conversions_12m,
                    feedback_immo_contacts_12m, feedback_immo_conversions_12m,
                    feedback_epargne_contacts_12m, feedback_epargne_conversions_12m
                )
                SELECT
                    c.radical_compte, %s, %s::date, 'real',
                    c."STATUT_CLIENT", c."Age", c."Region", c."Segment_actuel", c."Qualite",
                    COALESCE(c.nb_transaction,0), COALESCE(c.vol_transaction,0),
                    COALESCE(c.nb_retrait_gab,0), COALESCE(c.vol_retrait_gab,0),
                    COALESCE(c.nb_transaction_ecom,0), COALESCE(c.vol_transaction_ecom,0),
                    COALESCE(c.nb_virement,0), COALESCE(c.vol_virement,0),
                    COALESCE(c.solde_moyen_depots,0), COALESCE(c.encours_global,0),
                    COALESCE(c.encours_conso,0), COALESCE(c.encours_immo,0),
                    COALESCE(c.montant_revenu,0),
                    CASE WHEN LOWER(TRIM(COALESCE(c."App_instaled",''))) IN ('oui','yes','1','true') THEN 1 ELSE 0 END,
                    CASE WHEN LOWER(TRIM(COALESCE(c."Premiere_connex",''))) IN ('oui','yes','1','true') THEN 1 ELSE 0 END,
                    c."Carte_Actuelle",
                    CASE LOWER(TRIM(COALESCE(c."Carte_Actuelle",'')))
                      WHEN 'silver' THEN 1 WHEN 'titanium' THEN 2 WHEN 'gold' THEN 2
                      WHEN 'platinium' THEN 3 WHEN 'platinum' THEN 3 WHEN 'black' THEN 3
                      WHEN 'infinite' THEN 4 WHEN 'carte visa infinite' THEN 4 ELSE 0 END,
                    CASE WHEN LOWER(TRIM(COALESCE(c."Epargne",''))) IN ('oui','yes','1','true') THEN 1 ELSE 0 END,
                    CASE
                      WHEN LOWER(TRIM(COALESCE(c.credit_conso,''))) IN ('oui','yes','1','true')
                        THEN CASE WHEN COALESCE(c.encours_conso,0) > 500 THEN 'active' ELSE 'finished' END
                      ELSE 'never' END,
                    CASE
                      WHEN LOWER(TRIM(COALESCE(c.credit_immo,''))) IN ('oui','yes','1','true')
                        THEN CASE WHEN COALESCE(c.encours_immo,0) > 1000 THEN 'active' ELSE 'finished' END
                      ELSE 'never' END,
                    CASE WHEN COALESCE(p.nb_transaction,0)=0 THEN 0 ELSE (COALESCE(c.nb_transaction,0)-p.nb_transaction)/GREATEST(ABS(p.nb_transaction),1) END,
                    CASE WHEN COALESCE(p.solde_moyen_depots,0)=0 THEN 0 ELSE (COALESCE(c.solde_moyen_depots,0)-p.solde_moyen_depots)/GREATEST(ABS(p.solde_moyen_depots),1) END,
                    CASE WHEN COALESCE(p.montant_revenu,0)=0 THEN 0 ELSE (COALESCE(c.montant_revenu,0)-p.montant_revenu)/GREATEST(ABS(p.montant_revenu),1) END,
                    CASE WHEN COALESCE(p.encours_conso,0)=0 THEN 0 ELSE (COALESCE(c.encours_conso,0)-p.encours_conso)/GREATEST(ABS(p.encours_conso),1) END,
                    CASE WHEN COALESCE(p.encours_immo,0)=0 THEN 0 ELSE (COALESCE(c.encours_immo,0)-p.encours_immo)/GREATEST(ABS(p.encours_immo),1) END,
                    COALESCE(f.card_contacts,0), COALESCE(f.card_conversions,0),
                    COALESCE(f.conso_contacts,0), COALESCE(f.conso_conversions,0),
                    COALESCE(f.immo_contacts,0), COALESCE(f.immo_conversions,0),
                    COALESCE(f.epargne_contacts,0), COALESCE(f.epargne_conversions,0)
                FROM clients c
                LEFT JOIN dm_product_training_monthly p
                  ON p.radical_compte=c.radical_compte AND p.annee_mois=%s
                LEFT JOIN feedback f ON f.radical_compte=c.radical_compte
                WHERE c."STATUT_CLIENT" IN ('Actif','Inactif')
                ON CONFLICT (radical_compte, annee_mois) DO UPDATE SET
                    observed_on=EXCLUDED.observed_on,
                    source='real',
                    statut_client=EXCLUDED.statut_client,
                    age=EXCLUDED.age,
                    region=EXCLUDED.region,
                    segment=EXCLUDED.segment,
                    qualite=EXCLUDED.qualite,
                    nb_transaction=EXCLUDED.nb_transaction,
                    vol_transaction=EXCLUDED.vol_transaction,
                    nb_retrait_gab=EXCLUDED.nb_retrait_gab,
                    vol_retrait_gab=EXCLUDED.vol_retrait_gab,
                    nb_transaction_ecom=EXCLUDED.nb_transaction_ecom,
                    vol_transaction_ecom=EXCLUDED.vol_transaction_ecom,
                    nb_virement=EXCLUDED.nb_virement,
                    vol_virement=EXCLUDED.vol_virement,
                    solde_moyen_depots=EXCLUDED.solde_moyen_depots,
                    encours_global=EXCLUDED.encours_global,
                    encours_conso=EXCLUDED.encours_conso,
                    encours_immo=EXCLUDED.encours_immo,
                    montant_revenu=EXCLUDED.montant_revenu,
                    app_installed=EXCLUDED.app_installed,
                    premiere_connex=EXCLUDED.premiere_connex,
                    carte_actuelle=EXCLUDED.carte_actuelle,
                    card_rank=EXCLUDED.card_rank,
                    epargne_active=EXCLUDED.epargne_active,
                    credit_conso_state=EXCLUDED.credit_conso_state,
                    credit_immo_state=EXCLUDED.credit_immo_state,
                    delta_transactions=EXCLUDED.delta_transactions,
                    delta_depots=EXCLUDED.delta_depots,
                    delta_revenu=EXCLUDED.delta_revenu,
                    delta_encours_conso=EXCLUDED.delta_encours_conso,
                    delta_encours_immo=EXCLUDED.delta_encours_immo,
                    feedback_carte_contacts_12m=EXCLUDED.feedback_carte_contacts_12m,
                    feedback_carte_conversions_12m=EXCLUDED.feedback_carte_conversions_12m,
                    feedback_conso_contacts_12m=EXCLUDED.feedback_conso_contacts_12m,
                    feedback_conso_conversions_12m=EXCLUDED.feedback_conso_conversions_12m,
                    feedback_immo_contacts_12m=EXCLUDED.feedback_immo_contacts_12m,
                    feedback_immo_conversions_12m=EXCLUDED.feedback_immo_conversions_12m,
                    feedback_epargne_contacts_12m=EXCLUDED.feedback_epargne_contacts_12m,
                    feedback_epargne_conversions_12m=EXCLUDED.feedback_epargne_conversions_12m,
                    updated_at=NOW()
                """,
                (run_date, run_date, month, run_date, prev_month),
            )
            return int(cur.rowcount or 0)


def _backfill_previous_targets(run_date: date) -> int:
    current_month = month_key(run_date)
    prev_month = previous_month_key(run_date)
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dm_product_training_monthly p
                SET
                    target_card_silver = CASE WHEN p.card_rank < 1 THEN CASE WHEN c.card_rank=1 THEN 1 ELSE 0 END ELSE NULL END,
                    target_card_titanium = CASE WHEN p.card_rank < 2 THEN CASE WHEN c.card_rank=2 THEN 1 ELSE 0 END ELSE NULL END,
                    target_card_platinium = CASE WHEN p.card_rank < 3 THEN CASE WHEN c.card_rank=3 THEN 1 ELSE 0 END ELSE NULL END,
                    target_card_infinite = CASE WHEN p.card_rank < 4 THEN CASE WHEN c.card_rank=4 THEN 1 ELSE 0 END ELSE NULL END,
                    target_epargne = CASE WHEN p.epargne_active=0 THEN CASE WHEN c.epargne_active=1 THEN 1 ELSE 0 END ELSE NULL END,
                    target_conso = CASE
                      WHEN p.credit_conso_state='active' THEN CASE WHEN c.encours_conso > p.encours_conso * 1.10 + 500 THEN 1 ELSE 0 END
                      ELSE CASE WHEN c.credit_conso_state='active' THEN 1 ELSE 0 END END,
                    target_immo = CASE
                      WHEN p.credit_immo_state='active' THEN CASE WHEN c.encours_immo > p.encours_immo * 1.05 + 5000 THEN 1 ELSE 0 END
                      ELSE CASE WHEN c.credit_immo_state='active' THEN 1 ELSE 0 END END,
                    updated_at=NOW()
                FROM dm_product_training_monthly c
                WHERE p.annee_mois=%s
                  AND c.annee_mois=%s
                  AND c.radical_compte=p.radical_compte
                  AND p.source='real'
                """,
                (prev_month, current_month),
            )
            return int(cur.rowcount or 0)


def ensure_current_snapshot(run_date: date) -> Dict[str, int]:
    rows = _snapshot_rows(run_date)
    backfilled = _backfill_previous_targets(run_date)
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM dm_product_training_monthly WHERE annee_mois=%s", (month_key(run_date),))
            total = int((cur.fetchone() or [0])[0] or 0)
    logger.info("Datamart produits prêt: month=%s rows=%s backfilled_previous=%s", month_key(run_date), total, backfilled)
    return {"rows_upserted": rows, "rows_current_month": total, "previous_targets_backfilled": backfilled}
