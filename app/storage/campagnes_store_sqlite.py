from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any, Dict, List, Optional

from app.storage.db import DB_PATH

TABLE_NAME = "campagnes"

# On garde un schéma "nouveau" (etat) pour les nouvelles DB,
# mais on reste compatible avec l'existant (etat_campagne) via détection.
CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id_campagne   TEXT PRIMARY KEY,
    nom_campagne  TEXT NOT NULL,
    id_modele     TEXT NOT NULL,
    id_cible      TEXT NOT NULL,
    date_debut    TEXT NOT NULL,
    date_fin      TEXT NOT NULL,
    etat          TEXT NOT NULL,
    date_creation TEXT NOT NULL
)
"""


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def _cols(cur: sqlite3.Cursor, table: str) -> List[str]:
    cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def _etat_col(cur: sqlite3.Cursor) -> str:
    """
    Retourne le nom réel de la colonne d'état dans la table campagnes.
    Compatible avec:
      - etat
      - etat_campagne
    """
    if not _table_exists(cur, TABLE_NAME):
        return "etat"  # valeur par défaut si table pas encore créée

    cols = set(_cols(cur, TABLE_NAME))
    if "etat" in cols:
        return "etat"
    if "etat_campagne" in cols:
        return "etat_campagne"
    # fallback
    return "etat"


def ensure_table() -> None:
    conn = _connect()
    cur = conn.cursor()

    # Si la table n'existe pas, on la crée avec le schéma CREATE_SQL
    if not _table_exists(cur, TABLE_NAME):
        cur.execute(CREATE_SQL)
        conn.commit()
        conn.close()
        return

    # Si elle existe déjà: on ne force pas de migration ici (tu veux éviter de casser)
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
) -> str:
    """
    Signature attendue par campagne_service.py
    Retourne id_campagne.
    Compatible avec DB existante (etat_campagne) ou nouvelle (etat).
    """
    ensure_table()
    conn = _connect()
    cur = conn.cursor()

    etat_col = _etat_col(cur)
    id_campagne = _new_id_campagne(cur)
    today = date.today().isoformat()

    # colonnes réelles présentes
    cols = set(_cols(cur, TABLE_NAME))

    # certains schémas anciens peuvent avoir etat_campagne au lieu de etat
    # et aussi date_creation peut exister sous un autre nom : ici on suppose date_creation OK
    # (si ce n'est pas le cas, on ajustera ensuite)
    if "date_creation" not in cols:
        # si pas de date_creation, on l'ignore plutôt que casser
        cur.execute(
            f"""
            INSERT INTO {TABLE_NAME} (
                id_campagne, nom_campagne, id_modele, id_cible,
                date_debut, date_fin, {etat_col}
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_campagne,
                (nom_campagne or "").strip(),
                str(id_modele),
                str(id_cible),
                str(date_debut),
                str(date_fin),
                str(etat_campagne),
            ),
        )
    else:
        cur.execute(
            f"""
            INSERT INTO {TABLE_NAME} (
                id_campagne, nom_campagne, id_modele, id_cible,
                date_debut, date_fin, {etat_col}, date_creation
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_campagne,
                (nom_campagne or "").strip(),
                str(id_modele),
                str(id_cible),
                str(date_debut),
                str(date_fin),
                str(etat_campagne),
                today,
            ),
        )

    conn.commit()
    conn.close()
    return id_campagne


def update_etat_campagne(id_campagne: str, new_etat: str) -> None:
    ensure_table()
    conn = _connect()
    cur = conn.cursor()
    etat_col = _etat_col(cur)
    cur.execute(
        f"UPDATE {TABLE_NAME} SET {etat_col} = ? WHERE id_campagne = ?",
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
    cur.execute(f"SELECT * FROM {TABLE_NAME} ORDER BY COALESCE(date_creation, date_debut) DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def list_campagnes_active() -> List[Dict[str, Any]]:
    """
    Campagnes "actives" pour les interfaces :
    - En cours
    - Planifiée
    (Annulée / Terminée exclues)
    Compatible avec colonne etat OU etat_campagne.
    """
    ensure_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    etat_col = _etat_col(cur)
    cur.execute(
        f"""
        SELECT * FROM {TABLE_NAME}
        WHERE {etat_col} IN ('En cours', 'Planifiée')
        ORDER BY date_debut DESC
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
