from __future__ import annotations

import sqlite3
from typing import Any, Dict, List

from app.storage.db import DB_PATH

TABLE_NAME = "clients_campagnes"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_table() -> None:
    """
    Table attendue par campagne_service.py + les queries dans campagne_service
    (ID_CAMPAGNE, Canal, Action, Etat_campagne, etc.)
    """
    conn = _connect()
    cur = conn.cursor()

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            Nom_campagne            TEXT,
            ID_CAMPAGNE             TEXT,
            Radical_compte          TEXT,
            statut_avant_campagne   TEXT,
            statut_actuel           TEXT,
            Etat_campagne           TEXT,
            NB_jour_campagne        INTEGER,
            ID_Action               TEXT,
            Canal                   TEXT,
            Action                  TEXT,
            Last_action             TEXT,
            Resultat_last_action    TEXT,
            Date_last_action        TEXT,
            NB_jour_last_action     INTEGER,
            NB_appel                INTEGER,
            NB_mail                 INTEGER,
            NB_sms                  INTEGER,
            NB_message              INTEGER,
            NB_approche_commercial  INTEGER,
            arriv_eche              TEXT DEFAULT 'Non',

            -- ✅ NEW (ne casse pas l'existant)
            date_debut_campagne     TEXT,
            nb_jour_debut_campagne  INTEGER
        )
        """
    )

    # Migration douce : ajoute arriv_eche si la table existait déjà sans la colonne
    try:
        cur.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN arriv_eche TEXT DEFAULT 'Non'")
    except Exception:
        pass

    # ✅ Migration douce : ajoute date_debut_campagne si absent
    try:
        cur.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN date_debut_campagne TEXT")
    except Exception:
        pass

    # ✅ Migration douce : ajoute nb_jour_debut_campagne si absent
    try:
        cur.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN nb_jour_debut_campagne INTEGER")
    except Exception:
        pass

    # indexes non bloquants
    try:
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_cc_idcamp ON {TABLE_NAME}(ID_CAMPAGNE)")
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_cc_radical ON {TABLE_NAME}(Radical_compte)")
    except Exception:
        pass

    conn.commit()
    conn.close()


def bulk_insert_clients(rows: List[Dict[str, Any]]) -> int:
    """
    Insère en masse les lignes construites dans campagne_service.create_campagne().
    Signature attendue: bulk_insert_clients(rows)
    """
    if not rows:
        return 0

    ensure_table()

    cols = [
        "Nom_campagne",
        "ID_CAMPAGNE",
        "Radical_compte",
        "statut_avant_campagne",
        "statut_actuel",
        "Etat_campagne",
        "NB_jour_campagne",
        "ID_Action",
        "Canal",
        "Action",
        "Last_action",
        "Resultat_last_action",
        "Date_last_action",
        "NB_jour_last_action",
        "NB_appel",
        "NB_mail",
        "NB_sms",
        "NB_message",
        "NB_approche_commercial",
        "arriv_eche",

        # ✅ NEW
        "date_debut_campagne",
        "nb_jour_debut_campagne",
    ]

    sql = f"""
        INSERT INTO {TABLE_NAME} ({", ".join(cols)})
        VALUES ({", ".join(["?"] * len(cols))})
    """

    values = []
    for r in rows:
        if "arriv_eche" not in r or r.get("arriv_eche") is None:
            r["arriv_eche"] = "Non"

        # ✅ NEW defaults (au moment de création campagne)
        # - Pour anciennes campagnes: on ne fait rien (elles ne passent pas ici)
        # - Pour nouvelles campagnes: on veut nb_jour_debut_campagne=0
        if "nb_jour_debut_campagne" not in r or r.get("nb_jour_debut_campagne") is None:
            r["nb_jour_debut_campagne"] = 0

        # date_debut_campagne peut être ""/None si tu veux; mais idéalement campaign_service la mettra
        if "date_debut_campagne" not in r:
            r["date_debut_campagne"] = None

        values.append([r.get(c) for c in cols])

    conn = _connect()
    cur = conn.cursor()
    cur.executemany(sql, values)
    conn.commit()

    n = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else len(values)
    conn.close()
    return int(n)


def set_clients_etat_for_campagne(id_campagne: str, etat: str) -> int:
    """
    Met à jour Etat_campagne pour toutes les lignes de la campagne.
    Signature attendue: set_clients_etat_for_campagne(id_campagne, etat)
    """
    ensure_table()
    conn = _connect()
    cur = conn.cursor()

    cur.execute(
        f"UPDATE {TABLE_NAME} SET Etat_campagne = ? WHERE ID_CAMPAGNE = ?",
        (etat, id_campagne),
    )
    conn.commit()

    n = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
    conn.close()
    return int(n)
