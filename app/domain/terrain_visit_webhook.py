from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.storage.runtime_db import RuntimeConnection, connect_runtime
from app.storage.postgres_db import table_exists
from app.domain.workflow_nav import find_bloc_by_id

CLIENTS_CAMPAGNES_TABLE = "clients_campagnes"
CLIENTS_TABLE = "clients"
CAMPAGNES_TABLE = "campagnes"
MODELES_TABLE = "modeles"

WEBHOOK_URL = (
    os.environ.get("TERRAIN_VISITS_WEBHOOK_URL")
    or "https://wafa-api.swiftnova.ma/api/webhooks/visits"
).strip()

_WORKER_THREAD: Optional[threading.Thread] = None
_WORKER_STOP = threading.Event()
_WORKER_GUARD = threading.Lock()


def _connect() -> RuntimeConnection:
    return connect_runtime()


def _norm_str(x: Any) -> str:
    return "" if x is None else str(x).strip()


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_dispatch_table(conn: RuntimeConnection) -> None:
    if not table_exists("external_visit_dispatches"):
        raise RuntimeError(
            "La table PostgreSQL 'external_visit_dispatches' est absente. "
            "Le schéma doit être appliqué via les migrations SQL."
        )


def _get_col(row: Dict[str, Any], *names: str) -> str:
    for name in names:
        if name in row and _norm_str(row.get(name)):
            return _norm_str(row.get(name))
    normalized = {str(k).lower().replace(" ", "").replace("_", ""): k for k in row.keys()}
    for name in names:
        key = name.lower().replace(" ", "").replace("_", "")
        real = normalized.get(key)
        if real and _norm_str(row.get(real)):
            return _norm_str(row.get(real))
    return ""


def _get_full_name(row: Dict[str, Any]) -> str:
    full = _get_col(row, "fullName", "FullName", "full_name", "nom_complet")
    if full:
        return full
    prenom = _get_col(row, "Prenom", "Prénom", "prenom", "first_name")
    nom = _get_col(row, "Nom", "nom", "last_name")
    return " ".join([x for x in [prenom, nom] if x]).strip()


def _load_row(conn: RuntimeConnection, id_campagne: str, radical_compte: str) -> Optional[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT cc.*, c.visitMode, c.visitPurpose, c.id_modele, c.type_campagne,
               c.etat_campagne AS campagne_master_etat, cl.*
        FROM clients_campagnes cc
        LEFT JOIN campagnes c ON c.id_campagne = cc.ID_CAMPAGNE
        LEFT JOIN clients cl ON cl.radical_compte = cc.Radical_compte
        WHERE TRIM(cc.ID_CAMPAGNE) = ? AND TRIM(cc.Radical_compte) = ?
        LIMIT 1
        """,
        (_norm_str(id_campagne), _norm_str(radical_compte)),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _load_block_description(conn: RuntimeConnection, id_modele: str, block_id: str) -> str:
    if not id_modele or not block_id:
        return ""
    cur = conn.cursor()
    cur.execute("SELECT liste_action FROM modeles WHERE id_modele = ? LIMIT 1", (id_modele,))
    row = cur.fetchone()
    if not row:
        return ""
    try:
        actions = json.loads(_norm_str(row["liste_action"]) or "[]")
    except Exception:
        actions = []
    block = find_bloc_by_id(actions, block_id)
    if not block:
        return ""
    return (
        _norm_str(block.get("Message"))
        or _norm_str(block.get("message"))
        or _norm_str(block.get("Description"))
        or _norm_str(block.get("description"))
        or _norm_str(block.get("Contenu"))
        or _norm_str(block.get("contenu"))
    )


def _build_payload(conn: RuntimeConnection, row: Dict[str, Any]) -> Dict[str, Any]:
    block_id = _norm_str(row.get("ID_Action"))
    description = _load_block_description(conn, _norm_str(row.get("id_modele")), block_id)
    return {
        "correlationId": _norm_str(row.get("ID_CAMPAGNE")),
        "externalClientId": _norm_str(row.get("Radical_compte") or row.get("radical_compte")),
        "blockId": block_id,
        "fullName": _get_full_name(row),
        "phone": _get_col(row, "Numero_Tel", "phone", "Telephone", "Téléphone", "tel"),
        "email": _get_col(row, "Mail", "email", "Email"),
        "region": _get_col(row, "region", "Region", "Région"),
        "agence": _get_col(row, "agence", "Agence"),
        "plannedDate": "",
        "visitMode": _norm_str(row.get("visitMode")),
        "visitPurpose": _norm_str(row.get("visitPurpose")),
        "objectifs": [{"description": description}],
    }


def enqueue_visit_for_client(id_campagne: str, radical_compte: str) -> Dict[str, Any]:
    """Enregistre une visite à envoyer sans faire d'appel HTTP dans la requête métier."""
    conn = _connect()
    try:
        _ensure_dispatch_table(conn)
        row = _load_row(conn, id_campagne, radical_compte)
        if not row:
            return {"ok": False, "error": "client_campagne_not_found"}
        if int(row.get("conversion") or 0) == 1:
            return {"ok": True, "queued": False, "skipped": True, "reason": "client_converted"}
        if _norm_str(row.get("type_campagne")) != "avec_action_terrain":
            return {"ok": True, "queued": False, "skipped": True, "reason": "not_terrain_campaign"}
        action = _norm_str(row.get("Action"))
        if action not in ("Directeur d'agence", "Conseiller client"):
            return {"ok": True, "queued": False, "skipped": True, "reason": "not_da_cc_action"}
        block_id = _norm_str(row.get("ID_Action"))
        if not block_id:
            return {"ok": False, "error": "missing_block_id"}
        queue = "da" if action == "Directeur d'agence" else "cc"
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO external_visit_dispatches (
                id_campagne, radical_compte, block_id, queue, status, error, sent_at,
                attempts, next_attempt_at, last_attempt_at, updated_at
            ) VALUES (?, ?, ?, ?, 'pending', NULL, NULL, 0, NULL, NULL, ?)
            ON CONFLICT (id_campagne, radical_compte, block_id)
            DO UPDATE SET
                queue = EXCLUDED.queue,
                status = CASE
                    WHEN external_visit_dispatches.status IN ('sent','pending','processing','error') THEN external_visit_dispatches.status
                    ELSE 'pending'
                END,
                error = CASE
                    WHEN external_visit_dispatches.status IN ('sent','processing','error') THEN external_visit_dispatches.error
                    ELSE NULL
                END,
                attempts = CASE
                    WHEN external_visit_dispatches.status IN ('sent','pending','processing','error') THEN external_visit_dispatches.attempts
                    ELSE 0
                END,
                next_attempt_at = CASE
                    WHEN external_visit_dispatches.status IN ('sent','pending','processing','error') THEN external_visit_dispatches.next_attempt_at
                    ELSE NULL
                END,
                updated_at = EXCLUDED.updated_at
            """,
            (_norm_str(id_campagne), _norm_str(radical_compte), block_id, queue, _now_iso()),
        )
        conn.commit()
        return {"ok": True, "queued": True, "status": "pending"}
    finally:
        conn.close()


def dispatch_pending_visits_for_campaign(id_campagne: str) -> Dict[str, Any]:
    """Met en file toutes les visites éligibles en une seule opération PostgreSQL."""
    conn = _connect()
    try:
        _ensure_dispatch_table(conn)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO external_visit_dispatches (
                id_campagne, radical_compte, block_id, queue, status, error, sent_at,
                attempts, next_attempt_at, last_attempt_at, updated_at
            )
            SELECT
                cc.ID_CAMPAGNE,
                cc.Radical_compte,
                cc.ID_Action,
                CASE WHEN cc.Action = 'Directeur d''agence' THEN 'da' ELSE 'cc' END,
                'pending', NULL, NULL, 0, NULL, NULL, ?
            FROM clients_campagnes cc
            INNER JOIN campagnes c ON c.id_campagne = cc.ID_CAMPAGNE
            WHERE cc.ID_CAMPAGNE = ?
              AND COALESCE(cc.row_status, 0) = 0
              AND COALESCE(c.etat_campagne, '') = 'En cours'
              AND COALESCE(cc.conversion, 0) <> 1
              AND COALESCE(c.type_campagne, '') = 'avec_action_terrain'
              AND COALESCE(cc.Action, '') IN ('Directeur d''agence', 'Conseiller client')
              AND COALESCE(cc.ID_Action, '') <> ''
            ON CONFLICT (id_campagne, radical_compte, block_id)
            DO UPDATE SET
                queue = EXCLUDED.queue,
                status = CASE
                    WHEN external_visit_dispatches.status IN ('sent','pending','processing','error') THEN external_visit_dispatches.status
                    ELSE 'pending'
                END,
                error = CASE
                    WHEN external_visit_dispatches.status IN ('sent','processing','error') THEN external_visit_dispatches.error
                    ELSE NULL
                END,
                attempts = CASE
                    WHEN external_visit_dispatches.status IN ('sent','pending','processing','error') THEN external_visit_dispatches.attempts
                    ELSE 0
                END,
                next_attempt_at = CASE
                    WHEN external_visit_dispatches.status IN ('sent','pending','processing','error') THEN external_visit_dispatches.next_attempt_at
                    ELSE NULL
                END,
                updated_at = EXCLUDED.updated_at
            """,
            (_now_iso(), _norm_str(id_campagne)),
        )
        affected = int(cur.rowcount or 0)
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                COUNT(*) FILTER (WHERE status = 'processing') AS processing,
                COUNT(*) FILTER (WHERE status = 'sent') AS sent,
                COUNT(*) FILTER (WHERE status = 'error') AS errors
            FROM external_visit_dispatches
            WHERE id_campagne = ?
            """,
            (_norm_str(id_campagne),),
        )
        stats = dict(cur.fetchone() or {})
        conn.commit()
        return {
            "ok": True,
            "queued": affected,
            "pending": int(stats.get("pending") or 0),
            "processing": int(stats.get("processing") or 0),
            "sent": int(stats.get("sent") or 0),
            "errors": int(stats.get("errors") or 0),
            "async": True,
        }
    finally:
        conn.close()


def _claim_next_dispatch() -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        _ensure_dispatch_table(conn)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, id_campagne, radical_compte, block_id, attempts
            FROM external_visit_dispatches
            WHERE (
                    status IN ('pending', 'error')
                    OR (status = 'processing' AND COALESCE(last_attempt_at, '') <= ?)
                  )
              AND COALESCE(attempts, 0) < 5
              AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
            ORDER BY id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """,
            ((datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"), _now_iso()),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            return None
        item = dict(row)
        cur.execute(
            """
            UPDATE external_visit_dispatches
            SET status='processing',
                attempts=COALESCE(attempts,0)+1,
                last_attempt_at=?,
                updated_at=?
            WHERE id=?
            """,
            (_now_iso(), _now_iso(), int(item["id"])),
        )
        conn.commit()
        return item
    finally:
        conn.close()


def _complete_dispatch(dispatch_id: int, *, status: str, payload: Dict[str, Any], error: str = "") -> None:
    conn = _connect()
    try:
        cur = conn.cursor()
        if status == "sent":
            cur.execute(
                """
                UPDATE external_visit_dispatches
                SET status='sent', payload_json=?, error=NULL, sent_at=?, next_attempt_at=NULL, updated_at=?
                WHERE id=?
                """,
                (json.dumps(payload, ensure_ascii=False), _now_iso(), _now_iso(), dispatch_id),
            )
        else:
            cur.execute("SELECT attempts FROM external_visit_dispatches WHERE id=?", (dispatch_id,))
            row = cur.fetchone()
            attempts = int((row or {}).get("attempts") or 1) if isinstance(row, dict) else int(row[0] or 1)
            delay_minutes = min(60, 2 ** max(0, attempts - 1))
            next_at = (datetime.now() + timedelta(minutes=delay_minutes)).strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                """
                UPDATE external_visit_dispatches
                SET status='error', payload_json=?, error=?, next_attempt_at=?, updated_at=?
                WHERE id=?
                """,
                (json.dumps(payload, ensure_ascii=False), _norm_str(error), next_at, _now_iso(), dispatch_id),
            )
        conn.commit()
    finally:
        conn.close()


def _send_claimed_dispatch(item: Dict[str, Any]) -> None:
    conn = _connect()
    payload: Dict[str, Any] = {}
    try:
        row = _load_row(conn, _norm_str(item.get("id_campagne")), _norm_str(item.get("radical_compte")))
        if not row:
            _complete_dispatch(int(item["id"]), status="error", payload={}, error="client_campagne_not_found")
            return
        if (
            int(row.get("conversion") or 0) == 1
            or int(row.get("row_status") or 0) != 0
            or _norm_str(row.get("campagne_master_etat")) != "En cours"
        ):
            cur = conn.cursor()
            cur.execute(
                "UPDATE external_visit_dispatches SET status='cancelled', error=NULL, updated_at=? WHERE id=?",
                (_now_iso(), int(item["id"])),
            )
            conn.commit()
            return
        # Le client peut avoir changé de bloc depuis sa mise en file.
        if _norm_str(row.get("ID_Action")) != _norm_str(item.get("block_id")):
            cur = conn.cursor()
            cur.execute(
                "UPDATE external_visit_dispatches SET status='cancelled', error='workflow_moved', updated_at=? WHERE id=?",
                (_now_iso(), int(item["id"])),
            )
            conn.commit()
            return
        payload = _build_payload(conn, row)
    finally:
        conn.close()

    req = urllib.request.Request(
        WEBHOOK_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            status_code = int(response.status)
            _ = response.read()
        if 200 <= status_code < 300:
            _complete_dispatch(int(item["id"]), status="sent", payload=payload)
        else:
            _complete_dispatch(int(item["id"]), status="error", payload=payload, error=f"HTTP {status_code}")
    except Exception as exc:
        _complete_dispatch(int(item["id"]), status="error", payload=payload, error=str(exc))


def send_visit_for_client(id_campagne: str, radical_compte: str) -> Dict[str, Any]:
    """Compatibilité historique : l'appel devient non bloquant et met en file."""
    return enqueue_visit_for_client(id_campagne, radical_compte)


def _worker_loop() -> None:
    idle_sleep = float(os.getenv("TERRAIN_WORKER_IDLE_SECONDS", "1.0") or "1.0")
    while not _WORKER_STOP.is_set():
        try:
            item = _claim_next_dispatch()
            if item is None:
                _WORKER_STOP.wait(timeout=max(0.2, idle_sleep))
                continue
            _send_claimed_dispatch(item)
        except Exception:
            # Important au premier déploiement : le conteneur API peut démarrer
            # quelques secondes avant l'application de la migration SQL 005.
            # Le worker attend puis retente au lieu de mourir définitivement.
            _WORKER_STOP.wait(timeout=5.0)


def start_terrain_dispatch_worker() -> Optional[threading.Thread]:
    global _WORKER_THREAD
    with _WORKER_GUARD:
        if _WORKER_THREAD is not None and _WORKER_THREAD.is_alive():
            return _WORKER_THREAD
        if str(os.getenv("TERRAIN_WORKER_ENABLED", "true")).strip().lower() in {"0", "false", "no", "off"}:
            return None
        _WORKER_STOP.clear()
        _WORKER_THREAD = threading.Thread(target=_worker_loop, name="terrain-dispatch-worker", daemon=True)
        _WORKER_THREAD.start()
        return _WORKER_THREAD


def stop_terrain_dispatch_worker() -> None:
    global _WORKER_THREAD
    with _WORKER_GUARD:
        _WORKER_STOP.set()
        thread = _WORKER_THREAD
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
        _WORKER_THREAD = None


def get_terrain_dispatch_status(id_campagne: str | None = None) -> Dict[str, Any]:
    conn = _connect()
    try:
        _ensure_dispatch_table(conn)
        cur = conn.cursor()
        where = ""
        params = []
        if _norm_str(id_campagne):
            where = " WHERE id_campagne = ?"
            params.append(_norm_str(id_campagne))
        cur.execute(
            f"""
            SELECT status, COUNT(*) AS n
            FROM external_visit_dispatches
            {where}
            GROUP BY status
            """,
            params,
        )
        counts = {str(r["status"]): int(r["n"] or 0) for r in cur.fetchall()}
        return {
            "worker_running": bool(_WORKER_THREAD and _WORKER_THREAD.is_alive()),
            "counts": counts,
        }
    finally:
        conn.close()


def cancel_visits_for_campaign(id_campagne: str, *, local_status: str = "cancelled") -> Dict[str, Any]:
    id_campagne = _norm_str(id_campagne)
    if not id_campagne:
        return {"ok": False, "error": "missing_id_campagne"}

    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT type_campagne FROM campagnes WHERE id_campagne = ? LIMIT 1", (id_campagne,))
        c = cur.fetchone()
        if not c:
            return {"ok": False, "error": "campagne_not_found", "id_campagne": id_campagne}
        if _norm_str(c["type_campagne"]) != "avec_action_terrain":
            return {"ok": True, "skipped": True, "reason": "not_terrain_campaign", "id_campagne": id_campagne}
        _ensure_dispatch_table(conn)
        # Tout ce qui n'a jamais été envoyé peut être annulé immédiatement.
        cur.execute(
            """
            UPDATE external_visit_dispatches
            SET status=?, error=NULL, next_attempt_at=NULL, updated_at=?
            WHERE id_campagne=? AND status IN ('pending','processing','error')
            """,
            (_norm_str(local_status) or "cancelled", _now_iso(), id_campagne),
        )
        local_unsent_cancelled = int(cur.rowcount or 0)
        cur.execute("SELECT COUNT(*) FROM external_visit_dispatches WHERE id_campagne=? AND status='sent'", (id_campagne,))
        local_sent_before = int(cur.fetchone()[0] or 0)
        conn.commit()
    finally:
        conn.close()

    # S'il n'y a rien d'envoyé, aucun appel externe n'est nécessaire.
    if local_sent_before == 0:
        return {
            "ok": True,
            "id_campagne": id_campagne,
            "local_unsent_cancelled": local_unsent_cancelled,
            "local_sent_before": 0,
            "local_released_for_resend": 0,
        }

    url = f"{WEBHOOK_URL.rstrip('/')}/{id_campagne}"
    req = urllib.request.Request(url, method="DELETE")
    external_ok = False
    status_code = None
    response_body = ""
    error = ""
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            status_code = int(response.status)
            response_body = response.read().decode("utf-8", errors="ignore")
        external_ok = 200 <= int(status_code or 0) < 300
    except Exception as exc:
        error = str(exc)

    local_released = 0
    if external_ok:
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE external_visit_dispatches
                SET status=?, error=NULL, next_attempt_at=NULL, updated_at=?
                WHERE id_campagne=? AND status='sent'
                """,
                (_norm_str(local_status) or "cancelled", _now_iso(), id_campagne),
            )
            local_released = int(cur.rowcount or 0)
            conn.commit()
        finally:
            conn.close()

    return {
        "ok": external_ok,
        "id_campagne": id_campagne,
        "url": url,
        "status_code": status_code,
        "response": response_body,
        "error": error,
        "local_unsent_cancelled": local_unsent_cancelled,
        "local_sent_before": local_sent_before,
        "local_released_for_resend": local_released,
    }

# =========================================================
# Compatibilité Outbound Engine générique (migration 010+)
# Les définitions ci-dessous remplacent les anciennes fonctions publiques.
# =========================================================
def build_visit_payload_for_dispatch(id_campagne: str, radical_compte: str, block_id: str) -> Dict[str, Any]:
    conn = _connect()
    try:
        row = _load_row(conn, id_campagne, radical_compte)
        if not row:
            raise RuntimeError("client_campagne_not_found")
        if _norm_str(row.get("ID_Action")) != _norm_str(block_id):
            raise RuntimeError("workflow_moved")
        return _build_payload(conn, row)
    finally:
        conn.close()


def post_visit_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    import hashlib
    idem_raw = "|".join((
        _norm_str(payload.get("correlationId")),
        _norm_str(payload.get("externalClientId")),
        _norm_str(payload.get("blockId")),
    )).encode("utf-8")
    idempotency_key = hashlib.sha256(idem_raw).hexdigest()
    req = urllib.request.Request(
        WEBHOOK_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Idempotency-Key": idempotency_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=float(os.getenv("TERRAIN_HTTP_TIMEOUT_SECONDS", "20") or "20")) as response:
        status_code = int(response.status)
        body = response.read().decode("utf-8", errors="ignore")
    if not 200 <= status_code < 300:
        raise RuntimeError(f"HTTP {status_code}: {body[:1000]}")
    return {"status_code": status_code, "body": body[:4000]}


def enqueue_visit_for_client(id_campagne: str, radical_compte: str) -> Dict[str, Any]:  # type: ignore[no-redef]
    from app.outbound.store import enqueue_single
    return enqueue_single(id_campagne, radical_compte, channel="TERRAIN")


def send_visit_for_client(id_campagne: str, radical_compte: str) -> Dict[str, Any]:  # type: ignore[no-redef]
    return enqueue_visit_for_client(id_campagne, radical_compte)


def dispatch_pending_visits_for_campaign(id_campagne: str) -> Dict[str, Any]:  # type: ignore[no-redef]
    from app.outbound.store import enqueue_candidates, stats
    queued = int(enqueue_candidates(id_campagne=id_campagne, channels=("TERRAIN",), limit_per_channel=5000).get("TERRAIN", 0))
    counts = stats(id_campagne=id_campagne, channel="TERRAIN")
    return {
        "ok": True,
        "queued": queued,
        "pending": int(counts.get("pending", 0)) + int(counts.get("retry", 0)),
        "processing": int(counts.get("processing", 0)),
        "sent": int(counts.get("waiting_callback", 0)) + int(counts.get("completed", 0)),
        "errors": int(counts.get("failed", 0)),
        "async": True,
    }


def get_terrain_dispatch_status(id_campagne: str | None = None) -> Dict[str, Any]:  # type: ignore[no-redef]
    from app.outbound.store import stats
    try:
        from app.outbound.worker import worker_status
        running = int(worker_status().get("running", {}).get("TERRAIN", 0)) > 0
    except Exception:
        running = False
    return {"worker_running": running, "counts": stats(id_campagne=id_campagne, channel="TERRAIN")}


def cancel_visits_for_campaign(id_campagne: str, *, local_status: str = "cancelled") -> Dict[str, Any]:  # type: ignore[no-redef]
    """Annule les visites non envoyées et demande l'annulation externe des envoyées."""
    from app.outbound.store import stats

    id_campagne = _norm_str(id_campagne)
    if not id_campagne:
        return {"ok": False, "error": "missing_id_campagne"}

    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT type_campagne FROM campagnes WHERE id_campagne=? LIMIT 1", (id_campagne,))
        campaign = cur.fetchone()
        if not campaign:
            return {"ok": False, "error": "campagne_not_found", "id_campagne": id_campagne}
        if _norm_str(campaign.get("type_campagne")) != "avec_action_terrain":
            return {"ok": True, "skipped": True, "reason": "not_terrain_campaign", "id_campagne": id_campagne}

        target_status = "paused" if "pause" in (_norm_str(local_status).lower()) else (_norm_str(local_status) or "cancelled")
        cur.execute(
            """
            UPDATE outbound_dispatches
            SET status=?, last_error=NULL, completed_at=CASE WHEN ?='paused' THEN NULL ELSE NOW() END, updated_at=NOW()
            WHERE id_campagne=? AND channel='TERRAIN' AND status IN ('pending','retry')
            """,
            (target_status, target_status, id_campagne),
        )
        local_unsent_cancelled = int(cur.rowcount or 0)
        cur.execute(
            "SELECT COUNT(*) AS n FROM outbound_dispatches WHERE id_campagne=? AND channel='TERRAIN' AND status='waiting_callback'",
            (id_campagne,),
        )
        sent_before = int((cur.fetchone() or {}).get("n") or 0)
        conn.commit()
    finally:
        conn.close()

    if sent_before == 0:
        return {
            "ok": True,
            "id_campagne": id_campagne,
            "local_unsent_cancelled": local_unsent_cancelled,
            "local_sent_before": 0,
            "local_released_for_resend": 0,
        }

    url = f"{WEBHOOK_URL.rstrip('/')}/{id_campagne}"
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=float(os.getenv("TERRAIN_HTTP_TIMEOUT_SECONDS", "20") or "20")) as response:
            status_code = int(response.status)
            body = response.read().decode("utf-8", errors="ignore")
        external_ok = 200 <= status_code < 300
        error = ""
    except Exception as exc:
        status_code = None
        body = ""
        external_ok = False
        error = str(exc)

    released = 0
    if external_ok:
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE outbound_dispatches
                SET status=?, completed_at=NOW(), updated_at=NOW(), last_error=NULL
                WHERE id_campagne=? AND channel='TERRAIN' AND status='waiting_callback'
                """,
                (target_status, id_campagne),
            )
            released = int(cur.rowcount or 0)
            conn.commit()
        finally:
            conn.close()

    return {
        "ok": external_ok,
        "id_campagne": id_campagne,
        "url": url,
        "status_code": status_code,
        "response": body,
        "error": error,
        "local_unsent_cancelled": local_unsent_cancelled,
        "local_sent_before": sent_before,
        "local_released_for_resend": released,
    }
