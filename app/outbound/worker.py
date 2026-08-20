from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, List

from app.outbound.store import (
    active_depth,
    claim_mail_finalize,
    claim_next,
    complete_mail_finalize,
    dispatch_is_current,
    enqueue_candidates,
    mark_failure,
    mark_network_sent,
    mark_obsolete,
    mark_success,
)

logger = logging.getLogger(__name__)

_STOP = threading.Event()
_GUARD = threading.Lock()
_THREADS: List[threading.Thread] = []


def _process_mail_finalize(item: Dict[str, Any]) -> None:
    from app.engine.traitement_mail_engine import finalize_mail_dispatch

    delivery_status = str(item.get("delivery_status") or item.get("status") or "")
    delivered = delivery_status not in {"failed", "finalizing_failed"}
    result = finalize_mail_dispatch(
        str(item.get("id_campagne") or ""),
        str(item.get("radical_compte") or ""),
        str(item.get("block_id") or ""),
        int(item.get("occurrence") or 0),
        delivered=delivered,
    )
    if not result.get("ok") and not result.get("already_applied"):
        raise RuntimeError(str(result))
    complete_mail_finalize(int(item["id"]), delivered=delivered)


def _process_mail(item: Dict[str, Any]) -> None:
    from app.engine.traitement_mail_engine import prepare_mail_dispatch, send_mail_dispatch

    if not dispatch_is_current(item):
        mark_obsolete(int(item["id"]))
        return

    prepared = prepare_mail_dispatch(
        str(item.get("id_campagne") or ""),
        str(item.get("radical_compte") or ""),
        str(item.get("block_id") or ""),
        int(item.get("occurrence") or 0),
    )
    if prepared.get("obsolete"):
        mark_obsolete(int(item["id"]), str(prepared.get("reason") or "obsolete"))
        return
    if not prepared.get("ok"):
        status = mark_failure(int(item["id"]), str(prepared.get("reason") or "mail_prepare_failed"))
        if status == "failed":
            final = dict(item)
            final["delivery_status"] = "failed"
            _process_mail_finalize(final)
        return

    ok, error = send_mail_dispatch(prepared)
    if not ok:
        status = mark_failure(int(item["id"]), error or "mail_send_failed")
        if status == "failed":
            final = dict(item)
            final["delivery_status"] = "failed"
            _process_mail_finalize(final)
        return

    # Persister d'abord l'effet externe : si le process meurt ensuite, un autre
    # worker finalisera le workflow sans renvoyer le mail.
    if not mark_network_sent(int(item["id"]), {"smtp": "accepted"}):
        return
    final = dict(item)
    final["delivery_status"] = "sent"
    _process_mail_finalize(final)


def _process_terrain(item: Dict[str, Any]) -> None:
    from app.domain.terrain_visit_webhook import build_visit_payload_for_dispatch, post_visit_payload

    if not dispatch_is_current(item):
        mark_obsolete(int(item["id"]))
        return
    try:
        payload = build_visit_payload_for_dispatch(
            str(item.get("id_campagne") or ""),
            str(item.get("radical_compte") or ""),
            str(item.get("block_id") or ""),
        )
        response = post_visit_payload(payload)
    except Exception as exc:
        mark_failure(int(item["id"]), str(exc))
        return

    mark_success(
        int(item["id"]),
        waiting_callback=True,
        response=json.dumps(response, ensure_ascii=False),
    )


def _channel_loop(channel: str) -> None:
    idle = max(0.05, float(os.getenv("OUTBOUND_WORKER_IDLE_SECONDS", "0.25") or "0.25"))
    stale = max(60, int(os.getenv("OUTBOUND_STALE_SECONDS", "300") or "300"))
    channel = channel.upper()
    while not _STOP.is_set():
        try:
            if channel == "MAIL":
                finalize_item = claim_mail_finalize(stale_seconds=stale)
                if finalize_item is not None:
                    try:
                        _process_mail_finalize(finalize_item)
                    except Exception:
                        logger.exception("Mail finalize failed: dispatch=%s", finalize_item.get("id"))
                    continue

            item = claim_next(channel, stale_seconds=stale)
            if item is None:
                _STOP.wait(timeout=idle)
                continue
            if channel == "MAIL":
                _process_mail(item)
            elif channel == "TERRAIN":
                _process_terrain(item)
            else:
                mark_obsolete(int(item["id"]), "unsupported_channel")
        except Exception:
            logger.exception("Outbound worker unavailable: channel=%s", channel)
            _STOP.wait(timeout=2.0)


def _producer_loop() -> None:
    interval = max(0.2, float(os.getenv("OUTBOUND_PRODUCER_INTERVAL_SECONDS", "0.5") or "0.5"))
    target = max(500, int(os.getenv("OUTBOUND_QUEUE_TARGET_DEPTH", "5000") or "5000"))
    batch = max(100, min(5000, int(os.getenv("OUTBOUND_PRODUCER_BATCH_SIZE", "1000") or "1000")))
    while not _STOP.is_set():
        try:
            depth = active_depth()
            capacity = max(0, target - depth)
            if capacity > 0:
                per_channel = max(1, min(batch, capacity // 2 if capacity > 1 else 1))
                enqueue_candidates(channels=("MAIL", "TERRAIN"), limit_per_channel=per_channel)
        except Exception:
            logger.exception("Outbound producer unavailable")
        _STOP.wait(timeout=interval)


def start_outbound_workers() -> List[threading.Thread]:
    global _THREADS
    with _GUARD:
        if any(t.is_alive() for t in _THREADS):
            return list(_THREADS)
        if str(os.getenv("OUTBOUND_WORKER_ENABLED", "true")).strip().lower() in {"0","false","no","off"}:
            return []

        mail_workers = max(1, min(8, int(os.getenv("OUTBOUND_MAIL_WORKERS", "2") or "2")))
        terrain_workers = max(1, min(16, int(os.getenv("OUTBOUND_TERRAIN_WORKERS", "4") or "4")))
        _STOP.clear()
        threads: List[threading.Thread] = []
        producer = threading.Thread(target=_producer_loop, name="outbound-producer", daemon=True)
        producer.start()
        threads.append(producer)
        for idx in range(mail_workers):
            t = threading.Thread(target=_channel_loop, args=("MAIL",), name=f"outbound-mail-{idx+1}", daemon=True)
            t.start()
            threads.append(t)
        for idx in range(terrain_workers):
            t = threading.Thread(target=_channel_loop, args=("TERRAIN",), name=f"outbound-terrain-{idx+1}", daemon=True)
            t.start()
            threads.append(t)
        _THREADS = threads
        return list(_THREADS)


def stop_outbound_workers() -> None:
    global _THREADS
    with _GUARD:
        _STOP.set()
        for t in _THREADS:
            if t.is_alive():
                t.join(timeout=5.0)
        _THREADS = []


def worker_status() -> Dict[str, Any]:
    names = [t.name for t in _THREADS if t.is_alive()]
    return {
        "enabled": str(os.getenv("OUTBOUND_WORKER_ENABLED", "true")).strip().lower() not in {"0","false","no","off"},
        "producer_running": "outbound-producer" in names,
        "running": {
            "MAIL": sum(1 for n in names if n.startswith("outbound-mail-")),
            "TERRAIN": sum(1 for n in names if n.startswith("outbound-terrain-")),
        },
        "queue_target_depth": max(500, int(os.getenv("OUTBOUND_QUEUE_TARGET_DEPTH", "5000") or "5000")),
    }
