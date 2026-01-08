from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List

from app.modeles.modele import Modele

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "clients.db")


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS modeles (
    ID_MODELE TEXT PRIMARY KEY,
    Nom_modele TEXT NOT NULL,
    variable_cible TEXT,
    Objectif TEXT,
    Date_creation DATE,
    liste_action TEXT,
    vers_cc TEXT,
    graphe_json TEXT
);
"""


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def ensure_modeles_table() -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(CREATE_TABLE_SQL)

    cur.execute("PRAGMA table_info(modeles)")
    cols = [r[1] for r in cur.fetchall()]

    if "vers_cc" not in cols:
        cur.execute("ALTER TABLE modeles ADD COLUMN vers_cc TEXT")
    if "graphe_json" not in cols:
        cur.execute("ALTER TABLE modeles ADD COLUMN graphe_json TEXT")

    conn.commit()
    conn.close()


def list_modeles() -> List[Dict[str, Any]]:
    ensure_modeles_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM modeles ORDER BY Date_creation DESC, ID_MODELE DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def insert_modele(modele: Modele) -> str:
    ensure_modeles_table()
    conn = _connect()
    cur = conn.cursor()

    if not modele.id_modele:
        cur.execute("SELECT COUNT(*) FROM modeles")
        n = cur.fetchone()[0] or 0
        modele.id_modele = f"M{n+1:06d}"

    cur.execute(
        """
        INSERT INTO modeles (
            ID_MODELE, Nom_modele, variable_cible, Objectif, Date_creation, liste_action, vers_cc, graphe_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            modele.id_modele,
            modele.nom_modele,
            modele.variable_cible,
            modele.objectif,
            modele.date_creation,
            modele.liste_action_json(),
            modele.vers_cc,
            modele.graphe_json_str(),
        ),
    )

    conn.commit()
    conn.close()
    return modele.id_modele


def _modele_locked_by_active_campaign(cur: sqlite3.Cursor, id_modele: str) -> Dict[str, Any] | None:
    """
    Retourne la campagne active (En cours/Planifiée) qui utilise ce modèle, sinon None.
    """
    # Assure table campagnes sans importer au top (évite effets de bord)
    from app.storage.campagnes_store_sqlite import ensure_table

    ensure_table()

    cur.execute(
        """
        SELECT id_campagne, nom_campagne, etat_campagne
        FROM campagnes
        WHERE id_modele = ?
          AND etat_campagne IN ('En cours', 'Planifiée')
        LIMIT 1
        """,
        (id_modele,),
    )
    r = cur.fetchone()
    if not r:
        return None
    # r peut être tuple (selon row_factory) -> on normalise
    try:
        return dict(r)  # si sqlite3.Row
    except Exception:
        return {"id_campagne": r[0], "nom_campagne": r[1], "etat_campagne": r[2]}


def delete_modele(id_modele: str) -> None:
    """
    Supprime un modèle SI (et seulement si) il n'est pas utilisé par une campagne active (En cours/Planifiée).
    Sinon -> RuntimeError explicite.
    """
    ensure_modeles_table()
    conn = _connect()
    cur = conn.cursor()

    lock = _modele_locked_by_active_campaign(cur, id_modele)
    if lock:
        conn.close()
        raise RuntimeError(
            f"Suppression impossible: le modèle {id_modele} est utilisé par la campagne "
            f"{lock.get('id_campagne')} ({lock.get('etat_campagne')})"
        )

    cur.execute("DELETE FROM modeles WHERE ID_MODELE = ?", (id_modele,))
    conn.commit()
    conn.close()


def get_modele(id_modele: str) -> Dict[str, Any] | None:
    ensure_modeles_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM modeles WHERE ID_MODELE = ?", (id_modele,))
    r = cur.fetchone()
    conn.close()
    return dict(r) if r else None


import pandas as pd


def load_db() -> pd.DataFrame:
    """
    Compatibilité: certains modules importent load_db().
    Retourne la table modeles sous forme de DataFrame.
    """
    rows = list_modeles()
    return pd.DataFrame(rows) if rows else pd.DataFrame()
