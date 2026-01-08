from __future__ import annotations

import os
import sqlite3
from datetime import date
from typing import Any, Dict, Optional

import requests

from app.crc.crc_output_store_sqlite import insert_crc_output, ensure_crc_output_table
from app.crc.crc_input_store_sqlite import ensure_crc_input_table  # ✅ crée crc_input si absent

from app.storage.campagnes_store_sqlite import get_campagne
from app.storage.modele_store_sqlite import get_modele
from app.storage.action_vers_cc_store_sqlite import (
    ensure_action_vers_cc_table,
    create_action_vers_cc_from_campaign,
)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "clients.db")

CRC_INPUT_TABLE = "crc_input"

API_URL = "https://vdcalls.vdcloud.net/api/make"
CALLER_ID = "+33186569190"
EXT = "6500000043"
TOKEN = "YJGDlos!è§(uytqsçàjlqksxèikqksdkjbhqsd(è!çakzjhbkadfuybclkjndjgvhgvd"


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _today_iso() -> str:
    return date.today().isoformat()


def get_next_crc_input_row() -> Optional[Dict[str, Any]]:
    """
    Prend la 1ère ligne selon l’ordre de crc_input.
    ✅ Si la table n'existe pas encore : on la crée et on retourne None.
    """
    ensure_crc_input_table()

    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        f"""
        SELECT *
        FROM {CRC_INPUT_TABLE}
        ORDER BY date_creation_campagne ASC,
                 COALESCE(date_last_action, '9999-12-31') ASC
        LIMIT 1
        """
    )
    r = cur.fetchone()
    conn.close()
    return dict(r) if r else None


def skip_current_row(id_campagne: str, radical_compte: str) -> None:
    """
    Skip = on retire la ligne de crc_input (pas de output).
    """
    ensure_crc_input_table()

    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        f"DELETE FROM {CRC_INPUT_TABLE} WHERE ID_CAMPAGNE = ? AND Radical_compte = ?",
        (id_campagne, radical_compte),
    )
    conn.commit()
    conn.close()


def _is_vers_cc_enabled_for_campaign(id_campagne: str) -> bool:
    """
    True si la campagne est liée à un modèle vers_cc == "Oui".
    """
    camp = get_campagne(id_campagne)
    if not camp:
        return False
    id_modele = str(camp.get("id_modele", "") or "").strip()
    if not id_modele:
        return False
    modele = get_modele(id_modele)
    if not modele:
        return False
    return str(modele.get("vers_cc", "") or "").strip().lower() == "oui"


def _push_to_output_with_result(row: Dict[str, Any], resultat_label: str) -> None:
    """
    Ajoute la ligne dans crc_output avec MAJ last/result/date/nb_jour_last_action.
    Puis retire la ligne de crc_input.
    """
    ensure_crc_output_table()

    row_out = dict(row)
    row_out["Last_action"] = row.get("Action", "")
    row_out["Resultat_last_action"] = resultat_label
    row_out["date_last_action"] = _today_iso()
    row_out["NB_jour_last_action"] = 0

    insert_crc_output(row_out)

    skip_current_row(row_out["ID_CAMPAGNE"], row_out["Radical_compte"])


def mark_joignable_succes(row: Dict[str, Any]) -> None:
    """
    ✅ Comportement actuel:
      - push crc_output + remove crc_input

    ✅ Nouveau comportement (vers_cc):
      - si modele.vers_cc == "Oui":
          - ajout dans action_vers_cc (infos client + modele)
          - Action dans crc_output passe à "En traitement CC"
    """
    ensure_crc_output_table()

    id_campagne = str(row.get("ID_CAMPAGNE", "") or "").strip()
    radical_compte = str(row.get("Radical_compte", "") or "").strip()

    # 1) Préparer la ligne output
    row_out = dict(row)
    row_out["Last_action"] = row.get("Action", "")
    row_out["Resultat_last_action"] = "Joignable avec succès"
    row_out["date_last_action"] = _today_iso()
    row_out["NB_jour_last_action"] = 0

    # 2) Si vers_cc activé: créer action_vers_cc + changer Action
    if id_campagne and radical_compte and _is_vers_cc_enabled_for_campaign(id_campagne):
        ensure_action_vers_cc_table()
        # upsert dans action_vers_cc (traitement = valeur courante de la colonne cible)
        create_action_vers_cc_from_campaign(id_campagne, radical_compte)

        # ✅ Action côté crc_output
        row_out["Action"] = "En traitement CC"

    # 3) Upsert output
    insert_crc_output(row_out)

    # 4) Retirer de crc_input
    skip_current_row(id_campagne, radical_compte)


def mark_joignable_sans_succes(row: Dict[str, Any]) -> None:
    _push_to_output_with_result(row, "Joignable sans succès")


def mark_injoignable(row: Dict[str, Any]) -> None:
    _push_to_output_with_result(row, "Injoignable")


def call_client_api(phone_number: str) -> Dict[str, Any]:
    """
    Appel API POST make call.
    """
    payload = {
        "ext": EXT,
        "phone": phone_number,
        "CallrId": CALLER_ID,
        "Tocken": TOKEN,
    }
    resp = requests.post(API_URL, json=payload, timeout=20)
    return {"status_code": resp.status_code, "text": resp.text}


def call_current_client(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Utilise le numéro du client depuis crc_input -> Numero_Tel.
    """
    phone = (row.get("Numero_Tel") or "").strip()
    if not phone:
        return {"status_code": 0, "text": "Numero_Tel vide: impossible d'appeler"}
    return call_client_api(phone)
