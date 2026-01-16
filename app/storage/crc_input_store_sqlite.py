from __future__ import annotations

import sqlite3
from typing import List, Dict, Any

from app.storage.db import DB_PATH

TABLE_NAME = "crc_input"

# ✅ Schéma queue standard (utilisé par crc_engine)
QUEUE_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
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


def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def _is_queue_schema(cols: List[str]) -> bool:
    required = {
        "ID_CAMPAGNE",
        "Radical_compte",
        "Numero_Tel",
        "Mail",
        "date_creation_campagne",
        "date_last_action",
        "ID_Action",
        "Canal",
        "Action",
        "Etat_campagne",
        "statut_avant_campagne",
        "statut_actuel",
    }
    return required.issubset(set(cols))


def ensure_crc_input_table() -> None:
    """
    Migration safe si crc_input ancien.
    """
    conn = _connect()
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (TABLE_NAME,))
    exists = cur.fetchone() is not None

    if not exists:
        cur.execute(QUEUE_SCHEMA_SQL)
        conn.commit()
        conn.close()
        return

    cols = _table_columns(conn, TABLE_NAME)
    if _is_queue_schema(cols):
        conn.close()
        return

    # --- migration safe ---
    cur.execute(f"ALTER TABLE {TABLE_NAME} RENAME TO {TABLE_NAME}_old")
    cur.execute(QUEUE_SCHEMA_SQL)

    old_cols = _table_columns(conn, f"{TABLE_NAME}_old")
    old = set(old_cols)

    has_old_id = "id_campagne" in old
    has_old_tel = "numero_tel" in old
    has_old_statut = "statut_actuel" in old

    if has_old_id:
        cur.execute(
            f"""
            INSERT OR REPLACE INTO {TABLE_NAME} (
                ID_CAMPAGNE, Radical_compte, Numero_Tel, Mail,
                date_creation_campagne, date_last_action,
                ID_Action, Canal, Action, Etat_campagne,
                statut_avant_campagne, statut_actuel
            )
            SELECT
                id_campagne,
                radical_compte,
                { "numero_tel" if has_old_tel else "''" },
                '' as Mail,
                '' as date_creation_campagne,
                '' as date_last_action,
                '' as ID_Action,
                '' as Canal,
                '' as Action,
                '' as Etat_campagne,
                '' as statut_avant_campagne,
                { "statut_actuel" if has_old_statut else "''" }
            FROM {TABLE_NAME}_old
            """
        )

    cur.execute(f"DROP TABLE {TABLE_NAME}_old")
    conn.commit()
    conn.close()


def clear_crc_input() -> None:
    ensure_crc_input_table()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {TABLE_NAME}")
    conn.commit()
    conn.close()


# =========================================================
# ✅ NOUVEAU : génération CRC depuis clients_campagnes
# =========================================================
def fill_crc_input_from_clients_campagnes(id_campagne: str) -> int:
    """
    CRC = clients dont:
      - Etat_campagne='En cours'
      - Action='Appeler'
    (source: clients_campagnes)
    """
    ensure_crc_input_table()

    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        f"""
        INSERT OR REPLACE INTO {TABLE_NAME} (
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
            COALESCE(cc.Date_last_action,'') as date_last_action,
            COALESCE(cc.ID_Action,'') as ID_Action,
            COALESCE(cc.Canal,'') as Canal,
            COALESCE(cc.Action,'') as Action,
            COALESCE(cc.Etat_campagne,'') as Etat_campagne,
            COALESCE(cc.statut_avant_campagne,'') as statut_avant_campagne,
            COALESCE(cc.statut_actuel,'') as statut_actuel
        FROM clients_campagnes cc
        LEFT JOIN clients cl ON cl.radical_compte = cc.Radical_compte
        LEFT JOIN campagnes c ON c.id_campagne = cc.ID_CAMPAGNE
        WHERE cc.ID_CAMPAGNE = ?
          AND COALESCE(cc.Etat_campagne,'') = 'En cours'
          AND COALESCE(cc.Action,'') = 'Appeler'
        """,
        (id_campagne,),
    )
    conn.commit()
    n = cur.rowcount if cur.rowcount is not None else 0
    conn.close()
    return int(n)
