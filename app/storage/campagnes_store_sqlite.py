from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any, Dict, List, Optional

from app.storage.db import DB_PATH

TABLE_NAME = "campagnes"

# ✅ Schéma STRICT aligné sur ta DB : Etat_campagne (et non etat / etat_campagne)
CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id_campagne   TEXT PRIMARY KEY,
    nom_campagne  TEXT NOT NULL,
    id_modele     TEXT NOT NULL,
    id_cible      TEXT NOT NULL,
    date_debut    TEXT NOT NULL,
    date_fin      TEXT NOT NULL,
    Etat_campagne TEXT NOT NULL,
    date_creation TEXT NOT NULL,
    description   TEXT
)
"""


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def ensure_table() -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(CREATE_SQL)
    conn.commit()
    conn.close()


def _new_id_campagne(cur: sqlite3.Cursor) -> str:
    cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
    n = cur.fetchone()[0] or 0
    return f"CP{n+1:06d}"


def insert_campagne(
    *,
    nom_campagne: str,
    id_modele: str,
    id_cible: str,
    date_debut: str,
    date_fin: str,
    etat_campagne: str,
    description: Optional[str] = None,
) -> str:
    """
    Signature attendue par campagne_service.py
    Retourne id_campagne.

    ✅ Strict: écrit dans Etat_campagne (colonne officielle).
    """
    ensure_table()
    conn = _connect()
    cur = conn.cursor()

    id_campagne = _new_id_campagne(cur)
    today = date.today().isoformat()

    nom_campagne_v = (nom_campagne or "").strip()
    description_v = None if description is None else (description or "").strip()

    cur.execute(
        f"""
        INSERT INTO {TABLE_NAME} (
            id_campagne,
            nom_campagne,
            id_modele,
            id_cible,
            date_debut,
            date_fin,
            Etat_campagne,
            date_creation,
            description
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            id_campagne,
            nom_campagne_v,
            str(id_modele),
            str(id_cible),
            str(date_debut),
            str(date_fin),
            str(etat_campagne),
            today,
            description_v,
        ),
    )

    conn.commit()
    conn.close()
    return id_campagne


def update_etat_campagne(id_campagne: str, new_etat: str) -> None:
    ensure_table()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE {TABLE_NAME} SET Etat_campagne = ? WHERE id_campagne = ?",
        (new_etat, id_campagne),
    )
    conn.commit()
    conn.close()


# ✅ Alias attendu par campagne_service.py
def update_etat(id_campagne: str, new_etat: str) -> None:
    update_etat_campagne(id_campagne, new_etat)


def get_campagne(id_campagne: str) -> Optional[Dict[str, Any]]:
    ensure_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {TABLE_NAME} WHERE id_campagne = ?", (id_campagne,))
    r = cur.fetchone()
    conn.close()
    return dict(r) if r else None


def list_all_campagnes() -> List[Dict[str, Any]]:
    ensure_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {TABLE_NAME} ORDER BY date_creation DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def list_campagnes_active() -> List[Dict[str, Any]]:
    """
    Campagnes "actives" pour les interfaces :
    - En cours
    - Planifiée
    (Annulée / Terminée exclues)
    ✅ Strict: filtre sur Etat_campagne
    """
    ensure_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT * FROM {TABLE_NAME}
        WHERE Etat_campagne IN ('En cours', 'Planifiée')
        ORDER BY date_debut DESC
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
