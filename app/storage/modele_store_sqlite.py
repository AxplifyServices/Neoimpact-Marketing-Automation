from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

import pandas as pd

from app.domain.modele import Modele
from app.storage.db import DB_PATH


# =========================================================
# Connexion
# =========================================================

def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


# =========================================================
# Table (nouveau schéma strict)
# =========================================================

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS modeles (
    id_modele TEXT PRIMARY KEY,
    nom_modele TEXT NOT NULL,
    date_creation TEXT,
    liste_action TEXT,
    graphe_json TEXT,
    ui_positions TEXT
);
"""


def ensure_modeles_table() -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(CREATE_TABLE_SQL)

        # --- NEW: migration légère si colonne manquante ---
    try:
        cur.execute("PRAGMA table_info(modeles)")
        cols = [r[1] for r in cur.fetchall()]  # name
        if "ui_positions" not in cols:
            cur.execute("ALTER TABLE modeles ADD COLUMN ui_positions TEXT")
    except Exception:
        pass

    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_modeles_date ON modeles(date_creation)")
    except Exception:
        pass

    conn.commit()
    conn.close()


# =========================================================
# Helpers
# =========================================================

def _next_modele_id(cur: sqlite3.Cursor) -> str:
    cur.execute("SELECT id_modele FROM modeles WHERE id_modele IS NOT NULL")
    ids = [str(r[0]) for r in cur.fetchall() if r and r[0]]

    nums: List[int] = []
    for x in ids:
        x = x.strip()
        if x.upper().startswith("M"):
            try:
                nums.append(int(x[1:]))
            except Exception:
                pass

    next_n = (max(nums) + 1) if nums else 1
    return f"M{next_n:06d}"


# =========================================================
# CRUD
# =========================================================

def list_modeles() -> List[Dict[str, Any]]:
    ensure_modeles_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id_modele, nom_modele, date_creation, liste_action, graphe_json, ui_positions
        FROM modeles
        ORDER BY date_creation DESC
        """
    )

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def load_db() -> pd.DataFrame:
    rows = list_modeles()
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def get_modele_dict(id_modele: str) -> Optional[Dict[str, Any]]:
    ensure_modeles_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id_modele, nom_modele, date_creation, liste_action, graphe_json, ui_positions
        FROM modeles
        WHERE id_modele = ?
        """,
        (id_modele,),
    )

    r = cur.fetchone()
    conn.close()
    return dict(r) if r else None


def insert_modele(modele: Modele) -> str:
    ensure_modeles_table()
    conn = _connect()
    cur = conn.cursor()

    if not modele.id_modele or not str(modele.id_modele).strip():
        modele.id_modele = _next_modele_id(cur)

    try:
         ui_positions_json = modele.ui_positions_str()
    except Exception:
         ui_positions_json = json.dumps(getattr(modele, "ui_positions", {}) or {}, ensure_ascii=False)

    try:
        liste_action_json = modele.liste_action_json()
    except Exception:
        liste_action_json = json.dumps(modele.liste_action or [], ensure_ascii=False)

    try:
        graphe_json = modele.graphe_json_str()
    except Exception:
        graphe_json = json.dumps(modele.graphe_json or {}, ensure_ascii=False)

    cur.execute(
        """
        INSERT INTO modeles (
            id_modele, nom_modele, date_creation, liste_action, graphe_json, ui_positions
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            modele.id_modele,
            modele.nom_modele,
            modele.date_creation,
            liste_action_json,
            graphe_json,
            ui_positions_json,  # NEW
        ),
    )

    conn.commit()
    conn.close()
    return str(modele.id_modele)


def delete_modele(id_modele: str) -> None:
    ensure_modeles_table()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM modeles WHERE id_modele = ?", (id_modele,))
    conn.commit()
    conn.close()


def update_modele_field(id_modele: str, field: str, value: Any) -> None:
    ensure_modeles_table()
    conn = _connect()
    cur = conn.cursor()

    allowed = {
        "nom_modele": "nom_modele",
        "date_creation": "date_creation",
        "liste_action": "liste_action",
        "graphe_json": "graphe_json",
        "ui_positions": "ui_positions",  # NEW
    }

    col = allowed.get(field)
    if not col:
        conn.close()
        raise ValueError(f"Champ non supporté: {field}")

    cur.execute(f"UPDATE modeles SET {col} = ? WHERE id_modele = ?", (value, id_modele))
    conn.commit()
    conn.close()


def dict_to_modele(d: Dict[str, Any]) -> Modele:
    try:
        liste_action = json.loads(d.get("liste_action") or "[]")
    except Exception:
        liste_action = []

    try:
        graphe = json.loads(d.get("graphe_json") or "{}")
    except Exception:
        graphe = {}

    try:
          ui_positions = json.loads(d.get("ui_positions") or "{}")
    except Exception:
          ui_positions = {}

    return Modele(
        id_modele=str(d.get("id_modele") or ""),
        nom_modele=str(d.get("nom_modele") or ""),
        date_creation=str(d.get("date_creation") or ""),
        liste_action=liste_action,
        graphe_json=graphe,
        ui_positions=ui_positions,
    )
