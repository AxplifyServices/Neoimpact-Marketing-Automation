from __future__ import annotations

import sqlite3
from typing import Any, Dict, List

from app.storage.db import DB_PATH

QUEUE_TABLE = "vers_cc"

QUEUE_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {QUEUE_TABLE} (
    ID_CAMPAGNE            TEXT NOT NULL,
    Radical_compte         TEXT NOT NULL,
    Numero_Tel             TEXT,
    Mail                   TEXT,
    date_creation_campagne TEXT,
    date_last_action       TEXT,
    ID_Action              TEXT,
    Canal                  TEXT,
    Action                 TEXT,
    Etat_campagne          TEXT,
    statut_avant_campagne  TEXT,
    statut_actuel          TEXT,
    PRIMARY KEY (ID_CAMPAGNE, Radical_compte)
);
"""


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def ensure_vers_cc_table() -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(QUEUE_SCHEMA_SQL)
    conn.commit()
    conn.close()


def fill_action_vers_cc_from_clients_campagnes(id_campagne: str) -> int:
    ensure_vers_cc_table()

    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        f"""
        INSERT OR REPLACE INTO {QUEUE_TABLE} (
            ID_CAMPAGNE, Radical_compte, Numero_Tel, Mail,
            date_creation_campagne, date_last_action,
            ID_Action, Canal, Action, Etat_campagne,
            statut_avant_campagne, statut_actuel
        )
        SELECT
            cc.ID_CAMPAGNE,
            cc.Radical_compte,
            cl.Numero_Tel,
            cl.Mail,
            COALESCE(c.date_debut,'') as date_creation_campagne,
            CASE WHEN COALESCE(cc.arriv_eche ,'') = 'Oui' THEN '0000-01-01 00:00:00' ELSE COALESCE(cc.Date_last_action,'') END as date_last_action,
            COALESCE(cc.ID_Action,'') as ID_Action,
            COALESCE(cc.Canal,'') as Canal,
            COALESCE(cc.Action,'') as Action,
            COALESCE(cc.Etat_campagne,'') as Etat_campagne,
            '' as statut_avant_campagne,
            '' as statut_actuel
        FROM clients_campagnes cc
        LEFT JOIN clients cl ON cl.radical_compte = cc.Radical_compte
        LEFT JOIN campagnes c ON c.id_campagne = cc.ID_CAMPAGNE
        WHERE cc.ID_CAMPAGNE = ?
          AND COALESCE(cc.Etat_campagne,'') = 'En cours'
          AND COALESCE(cc.Action,'') = 'Conseiller client'
        """,
        (id_campagne,),
    )
    conn.commit()
    n = cur.rowcount if cur.rowcount is not None else 0
    conn.close()
    return int(n)
