from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "clients.db")

TABLE_NAME = "traitement_mail"


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def ensure_traitement_mail_table() -> None:
    conn = _connect()
    cur = conn.cursor()

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            ID_CAMPAGNE            TEXT NOT NULL,
            Radical_compte         TEXT NOT NULL,

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

            Resultat_transmission  TEXT,   -- transmit | non transmit (...)
            Date_transmission      TEXT,   -- ISO datetime

            PRIMARY KEY (ID_CAMPAGNE, Radical_compte)
        );
        """
    )

    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_camp ON {TABLE_NAME}(ID_CAMPAGNE)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_rc ON {TABLE_NAME}(Radical_compte)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_etat ON {TABLE_NAME}(Etat_campagne)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_action ON {TABLE_NAME}(Action)")

    conn.commit()
    conn.close()


def refresh_traitement_mail() -> int:
    """
    Remplit traitement_mail avec:
      - Etat_campagne = 'En cours'
      - Action = 'Message' (case-insensitive)
      - Mail non vide (depuis table clients)

    Source:
      clients_campagnes cc
      clients cl  (Mail)
      campagnes ca (date_creation)
    """
    ensure_traitement_mail_table()

    conn = _connect()
    cur = conn.cursor()

    cur.execute(f"DELETE FROM {TABLE_NAME}")

    sql = f"""
    INSERT INTO {TABLE_NAME} (
        ID_CAMPAGNE, Radical_compte,
        Mail,
        date_creation_campagne, date_last_action,
        ID_Action, Action,
        Etat_campagne,
        statut_avant_campagne, statut_actuel,
        Last_action, Resultat_last_action,
        Resultat_transmission, Date_transmission
    )
    SELECT
        cc.ID_CAMPAGNE,
        cc.Radical_compte,

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

        NULL AS Resultat_transmission,
        NULL AS Date_transmission
    FROM clients_campagnes cc
    LEFT JOIN clients cl
           ON cl.radical_compte = cc.Radical_compte
    LEFT JOIN campagnes ca
           ON ca.id_campagne = cc.ID_CAMPAGNE
    WHERE
        cc.Etat_campagne = 'En cours'
        AND LOWER(COALESCE(cc.Action, '')) = 'Message'
        AND TRIM(COALESCE(cl.Mail, '')) <> ''
    ORDER BY
        ca.date_creation ASC,
        COALESCE(cc.Date_last_action, '9999-12-31') ASC
    ;
    """

    cur.execute(sql)
    conn.commit()

    cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
    n = cur.fetchone()[0] or 0

    conn.close()
    return int(n)


def load_traitement_mail() -> List[Dict[str, Any]]:
    ensure_traitement_mail_table()

    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        f"""
        SELECT *
        FROM {TABLE_NAME}
        ORDER BY date_creation_campagne ASC,
                 COALESCE(date_last_action, '9999-12-31') ASC
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
