from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

import pandas as pd

from app.domain.modele import Modele
from app.storage.db import DB_PATH  # ✅ source unique DB


# =========================================================
# Helpers (schema detection + normalization)
# =========================================================
def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def _has_cols(cols: List[str], required: List[str]) -> bool:
    s = set(cols)
    return all(c in s for c in required)


def _detect_modele_schema(conn: sqlite3.Connection) -> str:
    """
    Retourne:
      - "new" si colonnes: id_modele, nom_modele, variable_cible, objectif, date_creation, liste_action, graphe_json
      - "legacy" si colonnes: ID_MODELE, Nom_modele, variable_cible, Objectif, Date_creation, liste_action, graphe_json
      - "unknown" sinon (fallback legacy)
    """
    cols = _table_columns(conn, "modeles")
    if _has_cols(
        cols,
        ["id_modele", "nom_modele", "variable_cible", "objectif", "date_creation", "liste_action", "graphe_json"],
    ):
        return "new"
    if _has_cols(
        cols,
        ["ID_MODELE", "Nom_modele", "variable_cible", "Objectif", "Date_creation", "liste_action", "graphe_json"],
    ):
        return "legacy"
    return "unknown"


def _norm_modele_row(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalise un dict DB -> clés standard (new)
    + ajoute les alias legacy utilisés dans l'UI.
    """
    out = {
        "id_modele": d.get("id_modele", d.get("ID_MODELE")),
        "nom_modele": d.get("nom_modele", d.get("Nom_modele")),
        "variable_cible": d.get("variable_cible"),
        "objectif": d.get("objectif", d.get("Objectif")),
        "date_creation": d.get("date_creation", d.get("Date_creation")),
        "liste_action": d.get("liste_action"),
        "graphe_json": d.get("graphe_json"),
    }

    # alias legacy (pour ne rien casser dans streamlit)
    out["ID_MODELE"] = out["id_modele"]
    out["Nom_modele"] = out["nom_modele"]
    out["Objectif"] = out["objectif"]
    out["Date_creation"] = out["date_creation"]

    return out


def _safe_json_dumps(x: Any, default: str) -> str:
    try:
        return json.dumps(x, ensure_ascii=False)
    except Exception:
        return default


def _next_modele_id(cur: sqlite3.Cursor, schema: str) -> str:
    """
    Génère un nouvel ID de type M000001 en prenant le max existant.
    """
    id_col = "id_modele" if schema == "new" else "ID_MODELE"

    cur.execute(f"SELECT {id_col} FROM modeles WHERE {id_col} IS NOT NULL AND TRIM({id_col}) <> ''")
    ids = [str(r[0]) for r in cur.fetchall() if r and r[0] is not None]

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
# Table modeles (NEW schema by default)
# =========================================================
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS modeles (
    id_modele TEXT PRIMARY KEY,
    nom_modele TEXT NOT NULL,
    variable_cible TEXT,
    objectif TEXT,
    date_creation TEXT,
    liste_action TEXT,
    graphe_json TEXT
);
"""


def ensure_modeles_table() -> None:
    """
    - Crée la table si absente (NEW schema).
    - Si table legacy existe déjà, on ne la modifie pas.
    """
    conn = _connect()
    cur = conn.cursor()
    cur.execute(CREATE_TABLE_SQL)

    # indexes (safe)
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_modeles_date ON modeles(date_creation)")
    except Exception:
        pass
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_modeles_Date ON modeles(Date_creation)")
    except Exception:
        pass

    conn.commit()
    conn.close()


# =========================================================
# CRUD
# =========================================================
def list_modeles() -> List[Dict[str, Any]]:
    ensure_modeles_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    schema = _detect_modele_schema(conn)
    cur = conn.cursor()

    if schema == "new":
        cur.execute(
            """
            SELECT id_modele, nom_modele, variable_cible, objectif, date_creation, liste_action, graphe_json
            FROM modeles
            ORDER BY date_creation DESC
            """
        )
    else:
        cur.execute(
            """
            SELECT ID_MODELE, Nom_modele, variable_cible, Objectif, Date_creation, liste_action, graphe_json
            FROM modeles
            ORDER BY Date_creation DESC
            """
        )

    rows = [_norm_modele_row(dict(r)) for r in cur.fetchall()]
    conn.close()
    return rows


def load_db() -> pd.DataFrame:
    rows = list_modeles()
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def get_modele_dict(id_modele: str) -> Optional[Dict[str, Any]]:
    ensure_modeles_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    schema = _detect_modele_schema(conn)
    cur = conn.cursor()

    if schema == "new":
        cur.execute(
            """
            SELECT id_modele, nom_modele, variable_cible, objectif, date_creation, liste_action, graphe_json
            FROM modeles
            WHERE id_modele = ?
            """,
            (id_modele,),
        )
    else:
        cur.execute(
            """
            SELECT ID_MODELE, Nom_modele, variable_cible, Objectif, Date_creation, liste_action, graphe_json
            FROM modeles
            WHERE ID_MODELE = ?
            """,
            (id_modele,),
        )

    r = cur.fetchone()
    conn.close()
    return _norm_modele_row(dict(r)) if r else None


# compat rétro
def get_modele_by_id(id_modele: str) -> Optional[Dict[str, Any]]:
    return get_modele_dict(id_modele)


def insert_modele(modele: Modele) -> str:
    """
    ✅ FIX ROOT CAUSE :
    - si modele.id_modele est None/"" -> génère un ID M000001...
    - puis insert selon schéma réel (new/legacy)
    """
    ensure_modeles_table()
    conn = _connect()
    schema = _detect_modele_schema(conn)
    if schema == "unknown":
        schema = "new"
    cur = conn.cursor()

    # ✅ Auto-ID robuste (empêche jamais d'insérer None)
    mid = getattr(modele, "id_modele", None)
    if mid is None or (isinstance(mid, str) and mid.strip() == ""):
        modele.id_modele = _next_modele_id(cur, schema)

    # serialisation JSON safe
    try:
        liste_action_json = (
            modele.liste_action_json()
            if hasattr(modele, "liste_action_json")
            else _safe_json_dumps(getattr(modele, "liste_action", []), "[]")
        )
    except Exception:
        liste_action_json = "[]"

    try:
        graphe_json = (
            modele.graphe_json_str()
            if hasattr(modele, "graphe_json_str")
            else _safe_json_dumps(getattr(modele, "graphe_json", {}), "{}")
        )
    except Exception:
        graphe_json = "{}"

    if schema == "new":
        cur.execute(
            """
            INSERT INTO modeles (
                id_modele, nom_modele, variable_cible, objectif, date_creation, liste_action, graphe_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                modele.id_modele,
                modele.nom_modele,
                modele.variable_cible,
                modele.objectif,
                modele.date_creation,
                liste_action_json,
                graphe_json,
            ),
        )
    else:
        cur.execute(
            """
            INSERT INTO modeles (
                ID_MODELE, Nom_modele, variable_cible, Objectif, Date_creation, liste_action, graphe_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                modele.id_modele,
                modele.nom_modele,
                modele.variable_cible,
                modele.objectif,
                modele.date_creation,
                liste_action_json,
                graphe_json,
            ),
        )

    conn.commit()
    conn.close()
    return str(modele.id_modele)


def delete_modele(id_modele: str) -> None:
    ensure_modeles_table()
    conn = _connect()
    schema = _detect_modele_schema(conn)
    cur = conn.cursor()
    if schema == "new":
        cur.execute("DELETE FROM modeles WHERE id_modele = ?", (id_modele,))
    else:
        cur.execute("DELETE FROM modeles WHERE ID_MODELE = ?", (id_modele,))
    conn.commit()
    conn.close()


def update_modele_field(id_modele: str, field: str, value: Any) -> None:
    ensure_modeles_table()
    conn = _connect()
    schema = _detect_modele_schema(conn)
    cur = conn.cursor()

    if schema == "new":
        mapping = {
            "id_modele": "id_modele",
            "nom_modele": "nom_modele",
            "variable_cible": "variable_cible",
            "objectif": "objectif",
            "date_creation": "date_creation",
            "liste_action": "liste_action",
            "graphe_json": "graphe_json",
            # legacy inputs
            "ID_MODELE": "id_modele",
            "Nom_modele": "nom_modele",
            "Objectif": "objectif",
            "Date_creation": "date_creation",
        }
        key_col = "id_modele"
    else:
        mapping = {
            "id_modele": "ID_MODELE",
            "nom_modele": "Nom_modele",
            "variable_cible": "variable_cible",
            "objectif": "Objectif",
            "date_creation": "Date_creation",
            "liste_action": "liste_action",
            "graphe_json": "graphe_json",
            # legacy inputs
            "ID_MODELE": "ID_MODELE",
            "Nom_modele": "Nom_modele",
            "Objectif": "Objectif",
            "Date_creation": "Date_creation",
        }
        key_col = "ID_MODELE"

    col = mapping.get(field)
    if not col:
        conn.close()
        raise ValueError(f"Champ non supporté: {field}")

    cur.execute(f"UPDATE modeles SET {col} = ? WHERE {key_col} = ?", (value, id_modele))
    conn.commit()
    conn.close()


def dict_to_modele(d: Dict[str, Any]) -> Modele:
    d = _norm_modele_row(d)

    try:
        liste_action = json.loads(d.get("liste_action") or "[]")
    except Exception:
        liste_action = []

    try:
        graphe = json.loads(d.get("graphe_json") or "{}")
    except Exception:
        graphe = {}

    # construction tolérante
    try:
        return Modele(
            id_modele=str(d.get("id_modele") or ""),
            nom_modele=str(d.get("nom_modele") or ""),
            variable_cible=str(d.get("variable_cible") or ""),
            objectif=str(d.get("objectif") or ""),
            date_creation=str(d.get("date_creation") or ""),
            liste_action=liste_action,
            graphe_json=graphe,
        )
    except TypeError:
        if hasattr(Modele, "new"):
            m = Modele.new(
                nom_modele=str(d.get("nom_modele") or ""),
                variable_cible=str(d.get("variable_cible") or ""),
                objectif=str(d.get("objectif") or ""),
                liste_action=liste_action,
                graphe_json=graphe,
            )
            m.id_modele = d.get("id_modele")
            return m
        raise
