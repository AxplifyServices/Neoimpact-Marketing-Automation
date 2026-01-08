from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "clients.db")

TABLE_NAME = "crc_input"

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


def ensure_crc_input_table() -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(CREATE_SQL)

    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_camp ON {TABLE_NAME}(ID_CAMPAGNE)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_rc ON {TABLE_NAME}(Radical_compte)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_action ON {TABLE_NAME}(Action)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_etat ON {TABLE_NAME}(Etat_campagne)")

    conn.commit()
    conn.close()


def refresh_crc_input() -> int:
    """
    Construit crc_input depuis:
      - clients_campagnes (filtrée)
      - clients (Numero_Tel, Mail) via Radical_compte
      - campagnes (date_creation) via ID_CAMPAGNE

    Filtres:
      - Etat_campagne = 'En cours'
      - Action = 'Appeler'

    Ordre:
      - date_creation_campagne ASC
      - date_last_action ASC (les vides à la fin)
    """
    ensure_crc_input_table()

    conn = _connect()
    cur = conn.cursor()

    # refresh contenu (structure durable)
    cur.execute(f"DELETE FROM {TABLE_NAME}")

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
    LEFT JOIN clients cl
           ON cl.radical_compte = cc.Radical_compte
    LEFT JOIN campagnes ca
           ON ca.id_campagne = cc.ID_CAMPAGNE
    WHERE
        cc.Etat_campagne = 'En cours'
        AND cc.Action = 'Appeler'
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


def load_crc_input() -> List[Dict[str, Any]]:
    ensure_crc_input_table()

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
