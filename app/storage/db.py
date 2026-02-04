from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import pandas as pd
import os
import sqlite3
import re
# =========================================================
# Source unique de vérité pour la base de données
# =========================================================

# Racine du projet (…/Marketing_automation_V2)
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

# Base par défaut : database.db à la racine du projet
# Possibilité d'override via variable d'environnement MA_DB_PATH
DB_PATH = os.environ.get(
    "MA_DB_PATH",
    os.path.join(PROJECT_ROOT, "database.db"),
)


def get_connection() -> sqlite3.Connection:
    """
    Ouvre une connexion SQLite vers la base courante.
    Aucune logique métier ici.
    """
    return sqlite3.connect(DB_PATH)

# ============================================================
# DATA ADMIN HELPERS (utilisés par l'interface Data_int)
# Dépendances: sqlite3, pandas, typing
# ============================================================




@dataclass
class NumericBounds:
    min: Optional[float] = None
    max: Optional[float] = None


@dataclass
class ColumnFilter:
    """
    Un seul type de filtre à la fois :
      - numeric: bornes min/max (None => pas de borne)
      - categorical: liste de modalités autorisées (vide/None => pas de filtre)
    """
    numeric: Optional[NumericBounds] = None
    categorical: Optional[List[str]] = None


# ---------- Petits helpers SQL ----------

def _quote_ident(name: str) -> str:
    """Quote un identifiant SQLite (table/col) pour éviter injections par nom."""
    return '"' + name.replace('"', '""') + '"'


def _to_float_or_none(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, str) and x.strip() == "":
        return None
    try:
        return float(x)
    except Exception:
        return None


def _normalize_cell_value_for_sqlite(v: Any) -> Any:
    """Convertit les NaN/NaT en None pour sqlite."""
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    return v


# ---------- Fonctions demandées ----------

def list_tables() -> List[str]:
    """Retourne la liste des tables utilisateur."""
    with get_connection() as conn:  # <- suppose que ton db.py a déjà connect()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    return [r[0] for r in rows]


def get_table_columns(table: str) -> List[Tuple[str, str]]:
    """
    Retourne [(col_name, col_type)] via PRAGMA table_info.
    """
    t = _quote_ident(table)
    with get_connection() as conn:
        rows = conn.execute(f"PRAGMA table_info({t})").fetchall()
    # PRAGMA table_info: cid, name, type, notnull, dflt_value, pk
    return [(r[1], (r[2] or "")) for r in rows]


def get_distinct_values(table: str, col: str, limit: int = 200) -> List[str]:
    """
    Récupère des modalités distinctes (stringifiées) pour une colonne.
    Limité pour éviter des dropdowns énormes.
    """
    t = _quote_ident(table)
    c = _quote_ident(col)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT DISTINCT {c} FROM {t} WHERE {c} IS NOT NULL LIMIT ?",
            (int(limit),),
        ).fetchall()
    # stringify + tri stable
    vals = []
    for (v,) in rows:
        if v is None:
            continue
        vals.append(str(v))
    vals = sorted(set(vals))
    return vals


def read_table(
    table: str,
    filters: Optional[Dict[str, ColumnFilter]] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> pd.DataFrame:
    """
    Lit une table + ajoute une colonne __rowid__ pour permettre update.
    Filtrage SQL paramétré.
    """
    t = _quote_ident(table)

    where_parts: List[str] = []
    params: List[Any] = []

    if filters:
        for col, f in filters.items():
            c = _quote_ident(col)
            if f is None:
                continue

            # Filtre numérique
            if f.numeric is not None:
                mn = _to_float_or_none(f.numeric.min)
                mx = _to_float_or_none(f.numeric.max)
                if mn is not None:
                    where_parts.append(f"CAST({c} AS REAL) >= ?")
                    params.append(mn)
                if mx is not None:
                    where_parts.append(f"CAST({c} AS REAL) <= ?")
                    params.append(mx)

            # Filtre catégoriel (multi)
            if f.categorical:
                # si liste vide => pas de filtre
                # comparaison en texte => robuste même si colonne est int
                placeholders = ",".join(["?"] * len(f.categorical))
                where_parts.append(f"CAST({c} AS TEXT) IN ({placeholders})")
                params.extend([str(x) for x in f.categorical])

    where_sql = ""
    if where_parts:
        where_sql = " WHERE " + " AND ".join(where_parts)

    limit_sql = ""
    if limit is not None:
        limit_sql = " LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])

    sql = f"SELECT rowid AS __rowid__, * FROM {t}{where_sql}{limit_sql}"

    with get_connection() as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    return df


def update_cell(table: str, rowid: int, col: str, value: Any) -> None:
    """
    Update 1 cellule via rowid.
    """
    t = _quote_ident(table)
    c = _quote_ident(col)

    v = _normalize_cell_value_for_sqlite(value)

    with get_connection() as conn:
        conn.execute(f"UPDATE {t} SET {c} = ? WHERE rowid = ?", (v, int(rowid)))
        conn.commit()


import re

import re
import sqlite3
from typing import Any, Dict, Tuple

def insert_client_if_new(data: Dict[str, Any]) -> Tuple[bool, str]:
    required_id = str(data.get("ID_Client") or "").strip()
    if not required_id:
        return False, "ID_Client obligatoire."

    with get_connection() as conn:
        cur = conn.cursor()

        # 🔒 Lock d’écriture pour éviter les collisions
        cur.execute("BEGIN IMMEDIATE")

        # Unicité ID_Client
        cur.execute("SELECT 1 FROM clients WHERE ID_Client = ? LIMIT 1", (required_id,))
        if cur.fetchone():
            conn.rollback()
            return False, f"ID_Client '{required_id}' existe déjà."

        # ✅ MAX numérique fiable sur RCxxxxxxxx
        cur.execute(
            """
            SELECT MAX(CAST(SUBSTR(radical_compte, 3) AS INTEGER))
            FROM clients
            WHERE radical_compte GLOB 'RC[0-9]*'
            """
        )
        max_num = cur.fetchone()[0]
        next_num = int(max_num or 0) + 1

        # 🔁 Retry en cas de collision UNIQUE
        for _ in range(20):
            radical = f"RC{next_num:08d}"
            data["radical_compte"] = radical

            cols = list(data.keys())
            placeholders = ", ".join(["?"] * len(cols))

            try:
                cur.execute(
                    f"INSERT INTO clients ({', '.join(cols)}) VALUES ({placeholders})",
                    [data.get(c) for c in cols],
                )
                conn.commit()
                return True, f"Client créé: {radical}"

            except sqlite3.IntegrityError as e:
                msg = str(e).lower()
                if "unique constraint failed" in msg and "clients.radical_compte" in msg:
                    next_num += 1
                    continue  # on retente
                conn.rollback()
                return False, f"Erreur insertion: {e}"

        conn.rollback()
        return False, "Impossible de générer un radical_compte unique."



