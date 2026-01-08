from __future__ import annotations

import os
import json
import sqlite3
from datetime import date
from typing import Any, Dict, List, Optional, Tuple


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "clients.db")


# -------------------------
# Helpers
# -------------------------
def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _today() -> date:
    return date.today()


def _today_iso() -> str:
    return _today().isoformat()


def _parse_date(d: Any) -> Optional[date]:
    if d is None:
        return None
    s = str(d).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        return None


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        return int(x)
    except Exception:
        return default


def _norm_str(x: Any) -> str:
    return str(x or "").strip()


def _norm_str_lower(x: Any) -> str:
    return _norm_str(x).lower()


# =========================================================
# 0) Campagnes: passage -> Terminée si date_fin dépassée
# =========================================================
def sync_campagnes_etat_by_end_date(today: Optional[date] = None) -> int:
    """
    Si date_fin < today => etat_campagne = 'Terminée'
    (Terminée = campagne sortie du périmètre: plus de CRC, plus de mails)
    """
    if today is None:
        today = _today()

    conn = _connect()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE campagnes
        SET etat_campagne = 'Terminée'
        WHERE
            TRIM(COALESCE(date_fin, '')) <> ''
            AND SUBSTR(date_fin, 1, 10) < ?
            AND LOWER(TRIM(COALESCE(etat_campagne, ''))) <> 'terminée'
            AND LOWER(TRIM(COALESCE(etat_campagne, ''))) <> 'terminee'
        """,
        (today.isoformat(),),
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


# =========================================================
# 1) Campagnes: passage Planifiée -> En cours si date_debut atteinte
# =========================================================
def sync_campagnes_etat_by_dates(today: Optional[date] = None) -> int:
    if today is None:
        today = _today()

    conn = _connect()
    cur = conn.cursor()

    # IMPORTANT: on ne force pas en cours si déjà Terminée ou Annulée
    cur.execute(
        """
        UPDATE campagnes
        SET etat_campagne = 'En cours'
        WHERE
            TRIM(COALESCE(date_debut, '')) <> ''
            AND SUBSTR(date_debut, 1, 10) <= ?
            AND (
                etat_campagne IS NULL
                OR TRIM(etat_campagne) = ''
                OR LOWER(etat_campagne) IN ('planifiée', 'planifiee')
            )
        """,
        (today.isoformat(),),
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


# =========================================================
# 2) Synchroniser Etat_campagne entre clients_campagnes et campagnes
# =========================================================
def sync_clients_campagnes_etat_from_campagnes() -> int:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE clients_campagnes
        SET Etat_campagne = (
            SELECT c.etat_campagne
            FROM campagnes c
            WHERE c.id_campagne = clients_campagnes.ID_CAMPAGNE
        )
        WHERE ID_CAMPAGNE IN (SELECT id_campagne FROM campagnes)
        """
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


# =========================================================
# 3) Recalcul NB_jour_* (campagne / last_action) sur clients_campagnes
# =========================================================
def refresh_days_counters_clients_campagnes(today: Optional[date] = None) -> int:
    if today is None:
        today = _today()

    conn = _connect()
    cur = conn.cursor()

    cur.execute("SELECT ID_CAMPAGNE, Radical_compte, Date_last_action FROM clients_campagnes")
    rows = cur.fetchall()

    updated = 0
    for r in rows:
        idc = r["ID_CAMPAGNE"]
        rc = r["Radical_compte"]
        dlast = _parse_date(r["Date_last_action"])
        nb_last = (today - dlast).days if dlast else None

        cur.execute("SELECT date_creation, date_debut FROM campagnes WHERE id_campagne = ? LIMIT 1", (idc,))
        camp = cur.fetchone()
        nb_camp = None
        if camp:
            d0 = _parse_date(camp["date_creation"]) or _parse_date(camp["date_debut"])
            if d0:
                nb_camp = max(0, (today - d0).days)

        cur.execute(
            """
            UPDATE clients_campagnes
            SET NB_jour_last_action = ?,
                NB_jour_campagne = COALESCE(?, NB_jour_campagne)
            WHERE ID_CAMPAGNE = ? AND Radical_compte = ?
            """,
            (nb_last, nb_camp, idc, rc),
        )
        updated += 1

    conn.commit()
    conn.close()
    return updated


# =========================================================
# 4) Cancellation rules
# =========================================================
def apply_cancellation_rules() -> int:
    conn = _connect()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE clients_campagnes
        SET Action = 'Canceled'
        WHERE Radical_compte IN (
            SELECT radical_compte
            FROM clients
            WHERE LOWER(TRIM(COALESCE(STATUT_CLIENT, ''))) = 'rupture de relation'
        )
        """
    )
    n1 = cur.rowcount

    cur.execute(
        """
        UPDATE clients_campagnes
        SET Action = 'Canceled'
        WHERE ID_CAMPAGNE IN (
            SELECT id_campagne
            FROM campagnes
            WHERE LOWER(TRIM(COALESCE(etat_campagne, ''))) IN ('annulée', 'annulee')
        )
        """
    )
    n2 = cur.rowcount

    conn.commit()
    conn.close()
    return n1 + n2


# =========================================================
# 5) Statut_actuel refresh + Closed uniquement si objectif atteint
# =========================================================
def refresh_statut_actuel_and_close_if_objectif_met() -> int:
    conn = _connect()
    cur = conn.cursor()

    cur.execute("SELECT ID_MODELE, variable_cible, Objectif FROM modeles")
    modele_map: Dict[str, Tuple[str, str]] = {
        r["ID_MODELE"]: (r["variable_cible"] or "", r["Objectif"] or "")
        for r in cur.fetchall()
    }

    cur.execute("SELECT id_campagne, id_modele FROM campagnes")
    camp_to_modele = {r["id_campagne"]: r["id_modele"] for r in cur.fetchall()}

    cur.execute("PRAGMA table_info(clients)")
    client_cols = {r[1] for r in cur.fetchall()}

    cur.execute("SELECT ID_CAMPAGNE, Radical_compte FROM clients_campagnes")
    rows = cur.fetchall()

    updated = 0
    for r in rows:
        idc = r["ID_CAMPAGNE"]
        rc = r["Radical_compte"]
        idm = camp_to_modele.get(idc, "")
        variable, objectif = modele_map.get(idm, ("", ""))

        variable = _norm_str(variable)
        objectif = _norm_str(objectif)

        if not variable or variable not in client_cols:
            continue

        cur.execute(f"SELECT [{variable}] FROM clients WHERE radical_compte = ? LIMIT 1", (rc,))
        cl = cur.fetchone()
        new_val = _norm_str(cl[0]) if cl else ""

        cur.execute(
            """
            UPDATE clients_campagnes
            SET statut_actuel = ?
            WHERE ID_CAMPAGNE = ? AND Radical_compte = ?
            """,
            (new_val, idc, rc),
        )
        updated += 1

        if objectif and _norm_str(new_val) == objectif:
            cur.execute(
                """
                UPDATE clients_campagnes
                SET Action = 'Closed'
                WHERE ID_CAMPAGNE = ? AND Radical_compte = ?
                """,
                (idc, rc),
            )

    conn.commit()
    conn.close()
    return updated


# =========================================================
# 6) Scenario helpers (liste_action + conditions)
# =========================================================
def _load_liste_action_for_campaign(cur: sqlite3.Cursor, id_campagne: str) -> List[Dict[str, Any]]:
    cur.execute(
        """
        SELECT m.liste_action
        FROM campagnes c
        JOIN modeles m ON m.ID_MODELE = c.id_modele
        WHERE c.id_campagne = ?
        """,
        (id_campagne,),
    )
    r = cur.fetchone()
    if not r:
        return []
    s = r[0] or ""
    try:
        blocks = json.loads(s) if s else []
        return blocks if isinstance(blocks, list) else []
    except Exception:
        return []


def _find_block(blocks: List[Dict[str, Any]], block_id: str) -> Optional[Dict[str, Any]]:
    bid = _norm_str(block_id)
    for b in blocks:
        if _norm_str(b.get("ID")) == bid:
            return b
    return None


def _children_blocks(blocks: List[Dict[str, Any]], parent_id: str) -> List[Dict[str, Any]]:
    pid = _norm_str(parent_id)
    return [b for b in blocks if _norm_str(b.get("Bloc_mere")) == pid]


def _eval_op(op: str, left: int, right: int) -> bool:
    op = _norm_str(op)
    if op == "=":
        return left == right
    if op == ">":
        return left > right
    if op == "<":
        return left < right
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    return False


def _match_conditions(
    cond_list: Any,
    *,
    resultat: str,
    nb_jour_last_action: Optional[int],
    nb_appel: int,
) -> bool:
    if not isinstance(cond_list, list) or not cond_list:
        return True

    for c in cond_list:
        if not isinstance(c, dict):
            continue
        field = _norm_str(c.get("field"))
        op = _norm_str(c.get("op"))
        value = c.get("value")

        if field == "Flag résultats":
            if _norm_str(resultat) != _norm_str(value):
                return False

        elif field == "Nombre Jour après last action":
            if nb_jour_last_action is None:
                return False
            if not _eval_op(op, int(nb_jour_last_action), _safe_int(value)):
                return False

        elif field == "NB_Appel":
            if not _eval_op(op, int(nb_appel), _safe_int(value)):
                return False

        else:
            return False

    return True


def _is_closed_node(block: Dict[str, Any]) -> bool:
    act = _norm_str_lower(block.get("Action"))
    bid = _norm_str_lower(block.get("ID"))
    return act == "closed" or bid.endswith("closed")


def compute_next_action_from_output(
    *,
    blocks: List[Dict[str, Any]],
    current_id_action: str,
    resultat_for_condition: str,
    nb_jour_last_action: Optional[int],
    nb_appel: int,
) -> Tuple[Optional[str], str]:
    children = _children_blocks(blocks, current_id_action)

    for child in children:
        if _is_closed_node(child):
            continue
        if _match_conditions(
            child.get("Condition"),
            resultat=resultat_for_condition,
            nb_jour_last_action=nb_jour_last_action,
            nb_appel=nb_appel,
        ):
            return _norm_str(child.get("ID")), _norm_str(child.get("Action"))

    return None, "En Attente"


def get_canal_for_id_action(blocks: List[Dict[str, Any]], id_action: str) -> str:
    b = _find_block(blocks, id_action)
    return _norm_str(b.get("Canal")) if b else ""


def _campagne_is_active(cur: sqlite3.Cursor, id_campagne: str) -> bool:
    """
    Active = En cours uniquement.
    Terminée / Annulée / Planifiée => on ne consomme plus les outputs.
    """
    cur.execute("SELECT etat_campagne FROM campagnes WHERE id_campagne = ? LIMIT 1", (id_campagne,))
    r = cur.fetchone()
    if not r:
        return False
    et = _norm_str_lower(r[0])
    return et == "en cours"


# =========================================================
# 7) Consommer crc_output -> MAJ clients_campagnes (uniquement si campagne active)
# =========================================================
def process_crc_output_and_update_clients_campagnes() -> int:
    conn = _connect()
    cur = conn.cursor()

    cur.execute("SELECT * FROM crc_output ORDER BY COALESCE(date_last_action,'9999-12-31') ASC")
    outs = cur.fetchall()
    processed = 0

    for o in outs:
        idc = _norm_str(o["ID_CAMPAGNE"])
        rc = _norm_str(o["Radical_compte"])
        if not idc or not rc:
            continue

        # ✅ campagne terminée/annulée => on ignore cette ligne d'output
        if not _campagne_is_active(cur, idc):
            continue

        blocks = _load_liste_action_for_campaign(cur, idc)

        id_action = _norm_str(o["ID_Action"])
        canal = get_canal_for_id_action(blocks, id_action)

        last_action = _norm_str(o["Last_action"])
        date_last_action = _norm_str(o["date_last_action"]) or _today_iso()
        resultat = _norm_str(o["Resultat_last_action"])

        cur.execute(
            """
            SELECT NB_appel, NB_sms, NB_mail, NB_message
            FROM clients_campagnes
            WHERE ID_CAMPAGNE = ? AND Radical_compte = ?
            """,
            (idc, rc),
        )
        rcc = cur.fetchone()
        if not rcc:
            continue

        nb_appel = _safe_int(rcc["NB_appel"])
        nb_sms = _safe_int(rcc["NB_sms"])
        nb_mail = _safe_int(rcc["NB_mail"])
        nb_msg = _safe_int(rcc["NB_message"])

        if _norm_str_lower(last_action) == "appeler":
            nb_appel += 1
        elif _norm_str_lower(last_action) == "message":
            c = _norm_str_lower(canal)
            if c == "sms":
                nb_sms += 1
            elif c.startswith("whatsapp"):
                nb_msg += 1
            elif c == "mail":
                nb_mail += 1

        nb_jour_last_action = 0

        new_id_action, new_action = compute_next_action_from_output(
            blocks=blocks,
            current_id_action=id_action,
            resultat_for_condition=resultat,
            nb_jour_last_action=nb_jour_last_action,
            nb_appel=nb_appel,
        )

        cur.execute(
            """
            UPDATE clients_campagnes
            SET
                Last_action = ?,
                Resultat_last_action = ?,
                Date_last_action = ?,
                NB_jour_last_action = ?,
                NB_appel = ?,
                NB_sms = ?,
                NB_mail = ?,
                NB_message = ?,
                ID_Action = ?,
                Action = ?
            WHERE ID_CAMPAGNE = ? AND Radical_compte = ?
            """,
            (
                last_action,
                resultat,
                date_last_action[:10],
                nb_jour_last_action,
                nb_appel,
                nb_sms,
                nb_mail,
                nb_msg,
                new_id_action,
                new_action,
                idc,
                rc,
            ),
        )
        processed += 1

    conn.commit()

    # Clean crc_output après batch (même les ignorées : tu as dit "clean output")
    cur.execute("DELETE FROM crc_output")
    conn.commit()
    conn.close()
    return processed


# =========================================================
# 8) Consommer output_mail (traitement_mail) -> MAJ clients_campagnes (uniquement si campagne active)
# =========================================================
def process_output_mail_and_update_clients_campagnes() -> int:
    conn = _connect()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM traitement_mail
        WHERE TRIM(COALESCE(Resultat_transmission, '')) <> ''
        ORDER BY COALESCE(Date_transmission, '9999-12-31') ASC
        """
    )
    outs = cur.fetchall()
    processed = 0

    for o in outs:
        idc = _norm_str(o["ID_CAMPAGNE"])
        rc = _norm_str(o["Radical_compte"])
        if not idc or not rc:
            continue

        if not _campagne_is_active(cur, idc):
            continue

        blocks = _load_liste_action_for_campaign(cur, idc)

        id_action = _norm_str(o["ID_Action"])
        canal = get_canal_for_id_action(blocks, id_action)

        last_action = "Message"
        resultat = _norm_str(o["Resultat_transmission"])
        date_last_action = (_norm_str(o["Date_transmission"]) or _today_iso())[:10]

        cur.execute(
            """
            SELECT NB_appel, NB_sms, NB_mail, NB_message
            FROM clients_campagnes
            WHERE ID_CAMPAGNE = ? AND Radical_compte = ?
            """,
            (idc, rc),
        )
        rcc = cur.fetchone()
        if not rcc:
            continue

        nb_appel = _safe_int(rcc["NB_appel"])
        nb_sms = _safe_int(rcc["NB_sms"])
        nb_mail = _safe_int(rcc["NB_mail"])
        nb_msg = _safe_int(rcc["NB_message"])

        c = _norm_str_lower(canal)
        if c == "sms":
            nb_sms += 1
        elif c.startswith("whatsapp"):
            nb_msg += 1
        elif c == "mail":
            nb_mail += 1

        nb_jour_last_action = 0

        new_id_action, new_action = compute_next_action_from_output(
            blocks=blocks,
            current_id_action=id_action,
            resultat_for_condition=resultat,
            nb_jour_last_action=nb_jour_last_action,
            nb_appel=nb_appel,
        )

        cur.execute(
            """
            UPDATE clients_campagnes
            SET
                Last_action = ?,
                Resultat_last_action = ?,
                Date_last_action = ?,
                NB_jour_last_action = ?,
                NB_appel = ?,
                NB_sms = ?,
                NB_mail = ?,
                NB_message = ?,
                ID_Action = ?,
                Action = ?
            WHERE ID_CAMPAGNE = ? AND Radical_compte = ?
            """,
            (
                last_action,
                resultat,
                date_last_action,
                nb_jour_last_action,
                nb_appel,
                nb_sms,
                nb_mail,
                nb_msg,
                new_id_action,
                new_action,
                idc,
                rc,
            ),
        )
        processed += 1

    conn.commit()

    # clean output_mail consommé
    cur.execute(
        """
        DELETE FROM traitement_mail
        WHERE TRIM(COALESCE(Resultat_transmission, '')) <> ''
        """
    )
    conn.commit()
    conn.close()
    return processed


# =========================================================
# 9) Rebuild crc_input depuis clients_campagnes (campagne active seulement)
# =========================================================
def rebuild_crc_input_from_clients_campagnes() -> int:
    conn = _connect()
    cur = conn.cursor()

    cur.execute("DELETE FROM crc_input")

    cur.execute(
        """
        INSERT INTO crc_input (
            ID_CAMPAGNE, Radical_compte,
            Numero_Tel, Mail,
            date_creation_campagne, date_last_action,
            ID_Action, Action,
            Etat_campagne,
            statut_avant_campagne, statut_actuel,
            Last_action, Resultat_last_action,
            NB_jour_campagne, NB_jour_last_action,
            NB_appel, NB_sms, NB_mail, NB_message
        )
        SELECT
            cc.ID_CAMPAGNE,
            cc.Radical_compte,
            cl.Numero_Tel,
            cl.Mail,
            ca.date_creation AS date_creation_campagne,
            cc.Date_last_action AS date_last_action,
            cc.ID_Action,
            cc.Action,
            cc.Etat_campagne,
            cc.statut_avant_campagne,
            cc.statut_actuel,
            cc.Last_action,
            cc.Resultat_last_action,
            cc.NB_jour_campagne,
            cc.NB_jour_last_action,
            cc.NB_appel,
            cc.NB_sms,
            cc.NB_mail,
            cc.NB_message
        FROM clients_campagnes cc
        LEFT JOIN clients cl ON cl.radical_compte = cc.Radical_compte
        LEFT JOIN campagnes ca ON ca.id_campagne = cc.ID_CAMPAGNE
        WHERE
            cc.Etat_campagne = 'En cours'
            AND cc.Action = 'Appeler'
        ORDER BY
            ca.date_creation ASC,
            COALESCE(cc.Date_last_action, '9999-12-31') ASC
        """
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


# =========================================================
# 10) Rebuild traitement_mail strict (campagne active + bloc courant mail)
# =========================================================
def rebuild_traitement_mail_queue_strict() -> int:
    conn = _connect()
    cur = conn.cursor()

    cur.execute("DELETE FROM traitement_mail")

    cur.execute(
        """
        SELECT cc.ID_CAMPAGNE, cc.Radical_compte, cc.ID_Action, cc.Action,
               cc.Etat_campagne, cc.statut_avant_campagne, cc.statut_actuel,
               cc.Last_action, cc.Resultat_last_action, cc.Date_last_action
        FROM clients_campagnes cc
        WHERE
            cc.Etat_campagne = 'En cours'
            AND LOWER(COALESCE(cc.Action, '')) = 'message'
        """
    )
    ccs = cur.fetchall()

    inserted = 0
    for r in ccs:
        idc = _norm_str(r["ID_CAMPAGNE"])
        rc = _norm_str(r["Radical_compte"])
        id_action = _norm_str(r["ID_Action"])

        blocks = _load_liste_action_for_campaign(cur, idc)
        canal = _norm_str_lower(get_canal_for_id_action(blocks, id_action))
        if canal != "mail":
            continue

        cur.execute("SELECT Mail FROM clients WHERE radical_compte = ? LIMIT 1", (rc,))
        cl = cur.fetchone()
        mail = _norm_str(cl[0]) if cl else ""
        if not mail:
            continue

        cur.execute("SELECT date_creation FROM campagnes WHERE id_campagne = ? LIMIT 1", (idc,))
        camp = cur.fetchone()
        date_creation = _norm_str(camp[0]) if camp else ""

        cur.execute(
            """
            INSERT OR REPLACE INTO traitement_mail (
                ID_CAMPAGNE, Radical_compte,
                Mail,
                date_creation_campagne, date_last_action,
                ID_Action, Action,
                Etat_campagne,
                statut_avant_campagne, statut_actuel,
                Last_action, Resultat_last_action,
                Resultat_transmission, Date_transmission
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
            """,
            (
                idc, rc,
                mail,
                date_creation,
                _norm_str(r["Date_last_action"]),
                id_action,
                _norm_str(r["Action"]),
                _norm_str(r["Etat_campagne"]),
                _norm_str(r["statut_avant_campagne"]),
                _norm_str(r["statut_actuel"]),
                _norm_str(r["Last_action"]),
                _norm_str(r["Resultat_last_action"]),
            ),
        )
        inserted += 1

    conn.commit()
    conn.close()
    return inserted


# =========================================================
# 11) Meta batch
# =========================================================
def run_batch_manuel(verbose: bool = True) -> Dict[str, int]:
    today = _today()

    out: Dict[str, int] = {}

    # ✅ 0) on termine d'abord les campagnes expirées
    out["campagnes_ended"] = sync_campagnes_etat_by_end_date(today=today)

    # ✅ 1) puis on démarre celles qui commencent
    out["campagnes_started"] = sync_campagnes_etat_by_dates(today=today)

    # ✅ 2) sync état vers clients_campagnes
    out["etat_synced"] = sync_clients_campagnes_etat_from_campagnes()

    out["canceled_applied"] = apply_cancellation_rules()
    out["statut_refreshed"] = refresh_statut_actuel_and_close_if_objectif_met()
    out["days_refreshed"] = refresh_days_counters_clients_campagnes(today=today)

    out["crc_output_processed"] = process_crc_output_and_update_clients_campagnes()
    out["mail_output_processed"] = process_output_mail_and_update_clients_campagnes()

    out["crc_input_rebuilt"] = rebuild_crc_input_from_clients_campagnes()
    out["mail_queue_rebuilt"] = rebuild_traitement_mail_queue_strict()

    try:
        from app.traitements.traitement_mail_engine import send_pending_mails
        out["mail_sent_ok"] = int(send_pending_mails(limit=9999) or 0)
        out["mail_sent_total"] = out["mail_sent_ok"]
    except Exception:
        out["mail_sent_ok"] = 0
        out["mail_sent_total"] = 0

    if verbose:
        print("[BATCH_MANUEL] done ->", out)

    return out


if __name__ == "__main__":
    run_batch_manuel(verbose=True)
