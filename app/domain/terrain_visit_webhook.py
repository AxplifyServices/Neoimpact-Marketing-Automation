from __future__ import annotations

import json
import os
import sqlite3
import urllib.request
from datetime import datetime
from typing import Any, Dict, Optional

from app.storage.db import DB_PATH
from app.domain.workflow_nav import find_bloc_by_id


CLIENTS_CAMPAGNES_TABLE = "clients_campagnes"
CLIENTS_TABLE = "clients"
CAMPAGNES_TABLE = "campagnes"
MODELES_TABLE = "modeles"

WEBHOOK_URL = (
    os.environ.get("TERRAIN_VISITS_WEBHOOK_URL")
    or "https://wafa-api.swiftnova.ma/api/webhooks/visits"
).strip()


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _norm_str(x: Any) -> str:
    return "" if x is None else str(x).strip()


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_dispatch_table(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS external_visit_dispatches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_campagne TEXT NOT NULL,
            radical_compte TEXT NOT NULL,
            block_id TEXT NOT NULL,
            queue TEXT,
            payload_json TEXT,
            status TEXT NOT NULL DEFAULT 'sent',
            error TEXT,
            sent_at TEXT,
            UNIQUE(id_campagne, radical_compte, block_id)
        )
        """
    )
    conn.commit()


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

def _load_row(conn: sqlite3.Connection, id_campagne: str, radical_compte: str) -> Optional[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            cc.*,
            c.visitMode,
            c.visitPurpose,
            c.id_modele,
            c.type_campagne,
            cl.*
        FROM clients_campagnes cc
        LEFT JOIN campagnes c ON c.id_campagne = cc.ID_CAMPAGNE
        LEFT JOIN clients cl ON cl.radical_compte = cc.Radical_compte
        WHERE TRIM(cc.ID_CAMPAGNE) = ?
          AND TRIM(cc.Radical_compte) = ?
        LIMIT 1
        """,
        (_norm_str(id_campagne), _norm_str(radical_compte)),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _load_block_description(conn: sqlite3.Connection, id_modele: str, block_id: str) -> str:
    if not id_modele or not block_id:
        return ""

    conn.row_factory = sqlite3.Row
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


def _already_sent(conn: sqlite3.Connection, id_campagne: str, radical_compte: str, block_id: str) -> bool:
    _ensure_dispatch_table(conn)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1
        FROM external_visit_dispatches
        WHERE id_campagne = ?
          AND radical_compte = ?
          AND block_id = ?
          AND status = 'sent'
        LIMIT 1
        """,
        (_norm_str(id_campagne), _norm_str(radical_compte), _norm_str(block_id)),
    )
    return cur.fetchone() is not None


def _insert_dispatch_log(
    conn: sqlite3.Connection,
    *,
    id_campagne: str,
    radical_compte: str,
    block_id: str,
    queue: str,
    payload: Dict[str, Any],
    status: str,
    error: str = "",
) -> None:
    _ensure_dispatch_table(conn)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO external_visit_dispatches (
            id_campagne,
            radical_compte,
            block_id,
            queue,
            payload_json,
            status,
            error,
            sent_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _norm_str(id_campagne),
            _norm_str(radical_compte),
            _norm_str(block_id),
            _norm_str(queue),
            json.dumps(payload, ensure_ascii=False),
            _norm_str(status),
            _norm_str(error),
            _now_iso(),
        ),
    )
    conn.commit()

def cancel_visits_for_campaign(id_campagne: str, *, local_status: str = "cancelled") -> Dict[str, Any]:
    """
    Supprime côté plateforme d'animation commerciale les tiers déjà affectés
    à une campagne, puis libère le log local pour permettre un renvoi
    après réactivation.

    API externe attendue:
      DELETE {WEBHOOK_URL}/{correlationId}

    Exemple:
      DELETE https://wafa-api.swiftnova.ma/api/webhooks/visits/CP00002
    """
    id_campagne = _norm_str(id_campagne)
    if not id_campagne:
        return {"ok": False, "error": "missing_id_campagne"}

    conn = _connect()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute(
            """
            SELECT type_campagne
            FROM campagnes
            WHERE id_campagne = ?
            LIMIT 1
            """,
            (id_campagne,),
        )
        c = cur.fetchone()

        if not c:
            return {
                "ok": False,
                "error": "campagne_not_found",
                "id_campagne": id_campagne,
            }

        if _norm_str(c["type_campagne"]) != "avec_action_terrain":
            return {
                "ok": True,
                "skipped": True,
                "reason": "not_terrain_campaign",
                "id_campagne": id_campagne,
            }

        _ensure_dispatch_table(conn)

        cur.execute(
            """
            SELECT COUNT(*)
            FROM external_visit_dispatches
            WHERE id_campagne = ?
              AND status = 'sent'
            """,
            (id_campagne,),
        )
        local_sent_before = int(cur.fetchone()[0] or 0)

    finally:
        conn.close()

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

    except Exception as e:
        error = str(e)

    # Important:
    # On libère les logs locaux uniquement si la suppression externe a réussi.
    # Sinon, on garde status='sent' pour éviter un renvoi qui pourrait créer
    # des doublons côté plateforme d'animation commerciale.
    local_released = 0

    if external_ok:
        conn = _connect()
        try:
            _ensure_dispatch_table(conn)
            cur = conn.cursor()

            cur.execute(
                """
                UPDATE external_visit_dispatches
                SET status = ?,
                    error = NULL
                WHERE id_campagne = ?
                  AND status = 'sent'
                """,
                (_norm_str(local_status) or "cancelled", id_campagne),
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
        "local_sent_before": local_sent_before,
        "local_released_for_resend": local_released,
    }

def send_visit_for_client(id_campagne: str, radical_compte: str) -> Dict[str, Any]:
    conn = _connect()
    try:
        row = _load_row(conn, id_campagne, radical_compte)
        if not row:
            return {"ok": False, "error": "client_campagne_not_found"}

        if _norm_str(row.get("type_campagne")) != "avec_action_terrain":
            return {"ok": True, "skipped": True, "reason": "not_terrain_campaign"}

        action = _norm_str(row.get("Action"))
        if action not in ("Directeur d'agence", "Conseiller client"):
            return {"ok": True, "skipped": True, "reason": "not_da_cc_action", "action": action}

        block_id = _norm_str(row.get("ID_Action"))
        if not block_id:
            return {"ok": False, "error": "missing_block_id"}

        if _already_sent(conn, id_campagne, radical_compte, block_id):
            return {"ok": True, "skipped": True, "reason": "already_sent"}

        queue = "da" if action == "Directeur d'agence" else "cc"

        description = _load_block_description(
            conn,
            _norm_str(row.get("id_modele")),
            block_id,
        )

        payload = {
            "correlationId": _norm_str(id_campagne),
            "externalClientId": _norm_str(radical_compte),
            "blockId": block_id,
            "fullName": _get_full_name(row),
            "phone": _get_col(row, "Numero_Tel", "phone", "Telephone", "Téléphone", "tel"),
            "email": _get_col(row, "Mail", "email", "Email"),
            "region": _get_col(row, "region", "Region", "Région"),
            "agence": _get_col(row, "agence", "Agence"),
            "plannedDate": "",
            "visitMode": _norm_str(row.get("visitMode")),
            "visitPurpose": _norm_str(row.get("visitPurpose")),
            "objectifs": [
                {
                    "description": description,
                }
            ],
        }

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            WEBHOOK_URL,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                status_code = int(response.status)
                body = response.read().decode("utf-8", errors="ignore")

            _insert_dispatch_log(
                conn,
                id_campagne=id_campagne,
                radical_compte=radical_compte,
                block_id=block_id,
                queue=queue,
                payload=payload,
                status="sent",
            )

            return {
                "ok": True,
                "sent": True,
                "status_code": status_code,
                "response": body,
                "payload": payload,
            }

        except Exception as e:
            _insert_dispatch_log(
                conn,
                id_campagne=id_campagne,
                radical_compte=radical_compte,
                block_id=block_id,
                queue=queue,
                payload=payload,
                status="error",
                error=str(e),
            )
            return {"ok": False, "error": str(e), "payload": payload}

    finally:
        conn.close()


def dispatch_pending_visits_for_campaign(id_campagne: str) -> Dict[str, Any]:
    conn = _connect()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT cc.ID_CAMPAGNE, cc.Radical_compte
            FROM clients_campagnes cc
            INNER JOIN campagnes c ON c.id_campagne = cc.ID_CAMPAGNE
            WHERE cc.ID_CAMPAGNE = ?
              AND COALESCE(cc.Etat_campagne, '') = 'En cours'
              AND COALESCE(c.type_campagne, '') = 'avec_action_terrain'
              AND COALESCE(cc.Action, '') IN ('Directeur d''agence', 'Conseiller client')
            """,
            (_norm_str(id_campagne),),
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    sent = 0
    skipped = 0
    errors = 0
    details = []

    for row in rows:
        res = send_visit_for_client(row["ID_CAMPAGNE"], row["Radical_compte"])
        details.append(res)

        if res.get("sent"):
            sent += 1
        elif res.get("ok"):
            skipped += 1
        else:
            errors += 1

    return {
        "ok": errors == 0,
        "sent": sent,
        "skipped": skipped,
        "errors": errors,
        "details": details,
    }