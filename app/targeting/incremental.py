from __future__ import annotations

import os
from typing import Any, Dict

from app.targeting.store import (
    advance_campaign_watermark,
    campaign_sync_lock,
    current_change_seq,
    fetch_changed_clients,
    get_campaign_state,
    initialize_campaign_state,
    mark_campaign_error,
)


def _batch_size() -> int:
    raw = int(os.getenv("TARGET_SYNC_CHANGE_BATCH_SIZE", "5000") or "5000")
    return max(100, min(10000, raw))


def sync_target_changes_for_campaign(
    id_campagne: str,
    *,
    bootstrap_if_needed: bool = True,
    wait_for_lock: bool = True,
) -> Dict[str, Any]:
    """Synchronise une campagne sans rescanner la totalité du datamart.

    - campagne historique/non initialisée : un rescan complet unique ;
    - ensuite : seulement les clients dont le ``change_seq`` dépasse le
      watermark de la campagne ;
    - toutes les insertions restent insert-only, donc les retries sont sûrs.
    """
    campaign_id = str(id_campagne or "").strip()
    if not campaign_id:
        return {"ok": False, "error": "id_campagne_missing"}

    from app.domain.campagne_service import sync_new_clients_from_cible_for_campaign

    with campaign_sync_lock(campaign_id, wait=wait_for_lock) as acquired:
        if not acquired:
            return {
                "ok": True,
                "busy": True,
                "new_cible_members": 0,
                "new_clients_campagne": 0,
                "changes_processed": 0,
            }

        state = get_campaign_state(campaign_id)
        initialized = bool(state.get("initialized"))

        if not initialized:
            if not bootstrap_if_needed:
                return {
                    "ok": False,
                    "error": "target_sync_not_initialized",
                    "new_cible_members": 0,
                    "new_clients_campagne": 0,
                    "changes_processed": 0,
                }

            # Capturé AVANT le SELECT massif : tout changement concurrent ayant
            # un seq supérieur sera retraité incrémentalement au prochain passage.
            start_seq = current_change_seq()
            result = sync_new_clients_from_cible_for_campaign(
                None,
                campaign_id,
                candidate_radicals=None,
            )
            if not result.get("ok"):
                mark_campaign_error(campaign_id, str(result.get("error") or "bootstrap_failed"))
                return {
                    **result,
                    "bootstrap": True,
                    "changes_processed": 0,
                    "watermark": int(state.get("watermark") or 0),
                }
            initialize_campaign_state(campaign_id, start_seq)
            return {
                **result,
                "bootstrap": True,
                "changes_processed": 0,
                "watermark": int(start_seq),
            }

        watermark = int(state.get("watermark") or 0)
        snapshot_seq = current_change_seq()
        if snapshot_seq <= watermark:
            return {
                "ok": True,
                "bootstrap": False,
                "new_cible_members": 0,
                "new_clients_campagne": 0,
                "changes_processed": 0,
                "watermark": watermark,
                "snapshot_seq": snapshot_seq,
            }

        new_cible_total = 0
        new_campaign_total = 0
        processed_total = 0
        batch_size = _batch_size()

        try:
            while watermark < snapshot_seq:
                rows = fetch_changed_clients(
                    after_seq=watermark,
                    through_seq=snapshot_seq,
                    limit=batch_size,
                )
                if not rows:
                    # Les lignes de cette plage ont pu recevoir un seq plus
                    # récent pendant le traitement. Elles réapparaîtront donc
                    # au-delà de snapshot_seq et ne sont pas perdues.
                    watermark = snapshot_seq
                    advance_campaign_watermark(campaign_id, watermark)
                    break

                radicals = [str(row.get("radical_compte") or "").strip() for row in rows]
                radicals = [value for value in radicals if value]
                max_seq = max(int(row.get("change_seq") or 0) for row in rows)

                if radicals:
                    result = sync_new_clients_from_cible_for_campaign(
                        None,
                        campaign_id,
                        candidate_radicals=radicals,
                    )
                    if not result.get("ok"):
                        raise RuntimeError(str(result.get("error") or "incremental_target_sync_failed"))
                    new_cible_total += int(result.get("new_cible_members") or 0)
                    new_campaign_total += int(result.get("new_clients_campagne") or 0)

                processed_total += len(rows)
                watermark = max(watermark, max_seq)
                advance_campaign_watermark(campaign_id, watermark)

            return {
                "ok": True,
                "bootstrap": False,
                "new_cible_members": int(new_cible_total),
                "new_clients_campagne": int(new_campaign_total),
                "changes_processed": int(processed_total),
                "watermark": int(watermark),
                "snapshot_seq": int(snapshot_seq),
            }
        except Exception as exc:
            mark_campaign_error(campaign_id, str(exc))
            return {
                "ok": False,
                "error": str(exc),
                "bootstrap": False,
                "new_cible_members": int(new_cible_total),
                "new_clients_campagne": int(new_campaign_total),
                "changes_processed": int(processed_total),
                "watermark": int(watermark),
                "snapshot_seq": int(snapshot_seq),
            }
