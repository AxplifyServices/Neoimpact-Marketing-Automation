from __future__ import annotations

import os
import json
import sqlite3
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Dict, List, Tuple, Optional

# lit automatiquement .env si présent
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from app.traitements.traitement_mail_store_sqlite import (
    ensure_traitement_mail_table,
    refresh_traitement_mail,
)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "clients.db")

# Gmail SMTP
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# ✅ Statuts EXACTS (comme ton modèle)
STATUS_OK = "Transmit"
STATUS_KO = "Non Transmit"


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _get_credentials() -> Tuple[str, str]:
    sender = (os.environ.get("MAIL_SENDER") or "").strip()
    password = (os.environ.get("MAIL_PASSWORD") or "").strip()
    if not sender or not password:
        raise RuntimeError("MAIL_SENDER / MAIL_PASSWORD manquants (mets-les dans .env).")
    if not sender.lower().endswith("@gmail.com"):
        raise RuntimeError("MAIL_SENDER doit être une adresse Gmail (@gmail.com) puisque tu veux envoyer via Gmail.")
    return sender, password


def _smtp_send(sender: str, password: str, to_email: str, subject: str, body: str) -> Tuple[bool, str]:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender, password)  # App Password Gmail
            server.send_message(msg)
        return True, "OK"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------
# MODELE -> récup template depuis modeles.liste_action
# ---------------------------------------------------------
def _get_liste_action_for_campagne(id_campagne: str) -> List[Dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT m.liste_action
            FROM campagnes c
            JOIN modeles m ON m.ID_MODELE = c.id_modele
            WHERE c.id_campagne = ?
            """,
            (id_campagne,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            raise RuntimeError(f"liste_action introuvable pour la campagne {id_campagne}")
        try:
            data = json.loads(row[0])
        except Exception as e:
            raise RuntimeError(f"liste_action JSON invalide pour campagne {id_campagne}: {e}")
        if not isinstance(data, list):
            raise RuntimeError("liste_action doit être une liste JSON")
        return [x for x in data if isinstance(x, dict)]
    finally:
        conn.close()


def _find_mail_block(liste_action: List[Dict[str, Any]], id_action: str) -> Dict[str, Any]:
    """
    Priorité :
    1) bloc dont ID == id_action
    2) fallback: premier bloc Canal=Mail & Action=Message
    """
    # 1) match exact par ID
    for b in liste_action:
        if str(b.get("ID", "")).strip() == str(id_action).strip():
            return b

    # 2) fallback mail/message
    for b in liste_action:
        canal = str(b.get("Canal") or "").strip().lower()
        action = str(b.get("Action") or "").strip().lower()
        if canal == "Mail" and action == "Message":
            return b

    return {}


def _extract_subject_body_from_block(block: Dict[str, Any]) -> Tuple[str, str]:
    subject = str(block.get("Objet") or "").strip()
    body = str(block.get("Contenu") or "").strip()
    return subject, body


def _get_client_context(radical_compte: str) -> Dict[str, str]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT radical_compte, Nom, Prenom, Mail
            FROM clients
            WHERE radical_compte = ?
            """,
            (radical_compte,),
        )
        row = cur.fetchone()
        if not row:
            return {"Radical_compte": radical_compte, "Nom": "", "Prenom": "", "Mail": ""}
        return {
            "Radical_compte": str(row["radical_compte"] or radical_compte),
            "Nom": str(row["Nom"] or ""),
            "Prenom": str(row["Prenom"] or ""),
            "Mail": str(row["Mail"] or ""),
        }
    finally:
        conn.close()


def _render_template(text: str, ctx: Dict[str, str]) -> str:
    out = text or ""
    for k, v in ctx.items():
        out = out.replace(f"{{{{{k}}}}}", v)
        out = out.replace(f"{{{{ {k} }}}}", v)
    return out


# ---------------------------------------------------------
# Résultats (IMPORTANT: Resultat_last_action = choix modèle)
# ---------------------------------------------------------
def _mark_result(id_campagne: str, rc: str, statut: str, detail: str = "") -> None:
    """
    - clients_campagnes.Resultat_last_action => uniquement 'Transmit' / 'Non Transmit'
    - traitement_mail.Resultat_transmission => on garde le détail technique
    """
    now = _now_iso()
    conn = _connect()
    cur = conn.cursor()
    try:
        tm_val = statut if not detail else f"{statut} ({detail})"

        cur.execute(
            """
            UPDATE traitement_mail
            SET Resultat_transmission = ?,
                Date_transmission = ?
            WHERE ID_CAMPAGNE = ?
              AND Radical_compte = ?
            """,
            (tm_val, now, id_campagne, rc),
        )

        # NB_mail existe dans ta base (vu dans schema)
        cur.execute(
            """
            UPDATE clients_campagnes
            SET Last_action = 'Mail',
                Resultat_last_action = ?,
                Date_last_action = ?,
                NB_mail = COALESCE(NB_mail, 0) + 1
            WHERE ID_CAMPAGNE = ?
              AND Radical_compte = ?
            """,
            (statut, now, id_campagne, rc),
        )

        conn.commit()
    finally:
        conn.close()


def send_pending_mails(limit: int = 9999) -> int:
    sender, password = _get_credentials()
    ensure_traitement_mail_table()

    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ID_CAMPAGNE, Radical_compte, Mail, ID_Action
        FROM traitement_mail
        WHERE COALESCE(Resultat_transmission, '') = ''
        ORDER BY date_creation_campagne ASC,
                 COALESCE(date_last_action, '9999-12-31') ASC
        LIMIT ?
        """,
        (int(limit),),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    sent = 0
    for r in rows:
        id_c = str(r["ID_CAMPAGNE"])
        rc = str(r["Radical_compte"])
        to_email = str(r.get("Mail") or "").strip()
        id_action = str(r.get("ID_Action") or "").strip()

        if not to_email:
            _mark_result(id_c, rc, STATUS_KO, "mail vide")
            continue

        # 1) récupérer liste_action + bloc mail correspondant
        try:
            liste_action = _get_liste_action_for_campagne(id_c)
            block = _find_mail_block(liste_action, id_action)
            if not block:
                raise RuntimeError(f"bloc Mail/Message introuvable (ID_Action={id_action})")
            subject_tpl, body_tpl = _extract_subject_body_from_block(block)
            if not body_tpl:
                raise RuntimeError("Contenu vide dans le bloc modèle")
            if not subject_tpl:
                subject_tpl = "Information"
        except Exception as e:
            _mark_result(id_c, rc, STATUS_KO, f"template KO: {e}")
            continue

        # 2) variables client
        ctx = _get_client_context(rc)
        subject = _render_template(subject_tpl, ctx)
        body = _render_template(body_tpl, ctx)

        ok, info = _smtp_send(sender, password, to_email, subject, body)
        if ok:
            _mark_result(id_c, rc, STATUS_OK)
            sent += 1
        else:
            _mark_result(id_c, rc, STATUS_KO, info)

    return sent


def refresh_and_send_mails(limit: int = 9999) -> Tuple[int, int]:
    n_refresh = refresh_traitement_mail()
    n_sent = send_pending_mails(limit=limit)
    return n_refresh, n_sent


if __name__ == "__main__":
    n_refresh, n_sent = refresh_and_send_mails()
    print(f"[MAIL] refreshed={n_refresh} | sent={n_sent}")
