from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional

from app.inbound.store import claim_next, complete, fail

logger = logging.getLogger(__name__)

_THREADS: List[threading.Thread] = []
_STOP = threading.Event()
_GUARD = threading.Lock()


def _payload(item: Dict[str, Any]) -> Dict[str, Any]:
    raw = item.get("payload_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _process(item: Dict[str, Any]) -> None:
    channel = str(item.get("channel") or "").upper()
    event_type = str(item.get("event_type") or "")
    data = _payload(item)

    if channel == "TERRAIN" and event_type == "visit_result":
        from app.engine.contact_client_engine import apply_result_from_queue

        resultats = data.get("resultats") or []
        resultat = str(resultats[0] if resultats else data.get("resultat") or "").strip()
        if resultat not in {"Aboutit", "Non Aboutit"}:
            raise ValueError("resultat terrain invalide")
        result = apply_result_from_queue(
            row={
                "ID_CAMPAGNE": str(item.get("id_campagne") or data.get("correlationId") or "").strip(),
                "Radical_compte": str(item.get("radical_compte") or data.get("externalClientId") or "").strip(),
                "ID_Action": str(item.get("block_id") or data.get("blockId") or "").strip(),
            },
            resultat_label=resultat,
            queue_table="outbound_dispatches",
        )
        if not result.get("ok"):
            # Les doublons déjà traités sont idempotents et ne doivent pas boucler.
            if result.get("error") in {"dispatch_already_completed", "client_already_converted"}:
                return
            raise RuntimeError(str(result))
        return

    raise RuntimeError(f"unsupported inbound event: {channel}/{event_type}")


def _loop() -> None:
    idle = max(0.2, float(os.getenv("INBOUND_WORKER_IDLE_SECONDS", "0.5") or "0.5"))
    stale = max(60, int(os.getenv("INBOUND_STALE_SECONDS", "300") or "300"))
    while not _STOP.is_set():
        try:
            item = claim_next(stale_seconds=stale)
            if item is None:
                _STOP.wait(timeout=idle)
                continue
            try:
                _process(item)
                complete(int(item["id"]))
            except Exception as exc:
                logger.exception("Inbound event failed: id=%s", item.get("id"))
                fail(int(item["id"]), str(exc))
        except Exception:
            logger.exception("Inbound worker unavailable")
            _STOP.wait(timeout=5.0)


def start_inbound_workers() -> List[threading.Thread]:
    global _THREADS
    with _GUARD:
        if any(t.is_alive() for t in _THREADS):
            return list(_THREADS)
        if str(os.getenv("INBOUND_WORKER_ENABLED", "true")).strip().lower() in {"0","false","no","off"}:
            return []
        count = max(1, min(8, int(os.getenv("INBOUND_WORKERS", "2") or "2")))
        _STOP.clear()
        _THREADS = []
        for idx in range(count):
            t = threading.Thread(target=_loop, name=f"inbound-worker-{idx+1}", daemon=True)
            t.start()
            _THREADS.append(t)
        return list(_THREADS)


def stop_inbound_workers() -> None:
    global _THREADS
    with _GUARD:
        _STOP.set()
        for t in _THREADS:
            if t.is_alive():
                t.join(timeout=5.0)
        _THREADS = []


def worker_status() -> Dict[str, Any]:
    return {
        "enabled": str(os.getenv("INBOUND_WORKER_ENABLED", "true")).strip().lower() not in {"0","false","no","off"},
        "configured": max(1, min(8, int(os.getenv("INBOUND_WORKERS", "2") or "2"))),
        "running": sum(1 for t in _THREADS if t.is_alive()),
    }
