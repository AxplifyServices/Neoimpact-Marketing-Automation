from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "clients.db")

TABLE_NAME = "crc_output"


CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    ID_CAMPAGNE            TEXT NOT NULL,
    Radical_compte         TEXT NOT NULL,

    Numero_Tel             TEXT,
    Mail                   TEXT,

    date_creation_campagne TEXT,
    date_last_action       TEXT,

    ID_Action              TEXT,
    Action                 TEXT,

    Etat_campagne          TEXT,

    statut_avant_campagne  TEXT,
    statut_actuel          TEXT,

    Last_action            TEXT,
    Resultat_last_action   TEXT,

    NB_jour_campagne       INTEGER,
    NB_jour_last_action    INTEGER,

    NB_appel               INTEGER,
    NB_sms                 INTEGER,
    NB_mail                INTEGER,
    NB_message             INTEGER,

    PRIMARY KEY (ID_CAMPAGNE, Radical_compte)
);
"""


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def ensure_crc_output_table() -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(CREATE_SQL)

    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_camp ON {TABLE_NAME}(ID_CAMPAGNE)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_rc ON {TABLE_NAME}(Radical_compte)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_etat ON {TABLE_NAME}(Etat_campagne)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_action ON {TABLE_NAME}(Action)")

    conn.commit()
    conn.close()


def insert_crc_output(row: Dict[str, Any]) -> None:
    """
    Insert/Upsert (si la ligne existe déjà, on écrase les champs).
    """
    ensure_crc_output_table()

    conn = _connect()
    cur = conn.cursor()

    sql = f"""
    INSERT INTO {TABLE_NAME} (
        ID_CAMPAGNE, Radical_compte,
        Numero_Tel, Mail,
        date_creation_campagne, date_last_action,
        ID_Action, Action,
        Etat_campagne,
        statut_avant_campagne, statut_actuel,
        Last_action, Resultat_last_action,
        NB_jour_campagne, NB_jour_last_action,
        NB_appel, NB_sms, NB_mail, NB_message
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(ID_CAMPAGNE, Radical_compte) DO UPDATE SET
        Numero_Tel=excluded.Numero_Tel,
        Mail=excluded.Mail,
        date_creation_campagne=excluded.date_creation_campagne,
        date_last_action=excluded.date_last_action,
        ID_Action=excluded.ID_Action,
        Action=excluded.Action,
        Etat_campagne=excluded.Etat_campagne,
        statut_avant_campagne=excluded.statut_avant_campagne,
        statut_actuel=excluded.statut_actuel,
        Last_action=excluded.Last_action,
        Resultat_last_action=excluded.Resultat_last_action,
        NB_jour_campagne=excluded.NB_jour_campagne,
        NB_jour_last_action=excluded.NB_jour_last_action,
        NB_appel=excluded.NB_appel,
        NB_sms=excluded.NB_sms,
        NB_mail=excluded.NB_mail,
        NB_message=excluded.NB_message
    """

    cur.execute(
        sql,
        (
            row.get("ID_CAMPAGNE"),
            row.get("Radical_compte"),
            row.get("Numero_Tel"),
            row.get("Mail"),
            row.get("date_creation_campagne"),
            row.get("date_last_action"),
            row.get("ID_Action"),
            row.get("Action"),
            row.get("Etat_campagne"),
            row.get("statut_avant_campagne"),
            row.get("statut_actuel"),
            row.get("Last_action"),
            row.get("Resultat_last_action"),
            row.get("NB_jour_campagne"),
            row.get("NB_jour_last_action"),
            row.get("NB_appel"),
            row.get("NB_sms"),
            row.get("NB_mail"),
            row.get("NB_message"),
        ),
    )

    conn.commit()
    conn.close()
