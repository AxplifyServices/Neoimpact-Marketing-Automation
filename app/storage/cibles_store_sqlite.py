from __future__ import annotations

import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple

import pandas as pd

from app.domain.cible import Cible
from app.storage.db import DB_PATH

# =========================================================
# CONFIG
# =========================================================
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Uploads cibles (fichiers plats)
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "uploads", "cibles")


# =========================================================
# CONNEXION
# =========================================================
def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# =========================================================
# TABLE
# =========================================================
def ensure_cibles_table() -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cibles (
            id_cible TEXT PRIMARY KEY,
            nom_cible TEXT NOT NULL,
            date_creation TEXT,
            source TEXT,
            filtre TEXT,
            chemin TEXT
        )
        """
    )
    conn.commit()
    conn.close()


# =========================================================
# IDS
# =========================================================
def _new_id_cible(cur: sqlite3.Cursor) -> str:
    cur.execute("SELECT id_cible FROM cibles ORDER BY id_cible DESC LIMIT 1")
    row = cur.fetchone()
    if not row:
        return "C000001"
    last = str(row[0])
    m = re.search(r"(\d+)$", last)
    n = int(m.group(1)) if m else 0
    return f"C{n+1:06d}"


# =========================================================
# CRUD
# =========================================================
def insert_cible(cible: Cible) -> str:
    """
    Insert cible dans sqlite.
    - Génère un id si vide
    """
    ensure_cibles_table()
    conn = _connect()
    cur = conn.cursor()

    if not cible.id_cible:
        cible.id_cible = _new_id_cible(cur)

    cible.validate()

    filtre_str = json.dumps(cible.filtre, ensure_ascii=False) if cible.source == "DB" else ""
    chemin = cible.chemin if cible.source == "Fichier plat" else ""

    cur.execute(
        """
        INSERT INTO cibles (id_cible, nom_cible, date_creation, source, filtre, chemin)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (cible.id_cible, cible.nom_cible, cible.date_creation, cible.source, filtre_str, chemin),
    )

    conn.commit()
    conn.close()
    return str(cible.id_cible)


def list_cibles() -> List[Dict[str, Any]]:
    ensure_cibles_table()
    conn = _connect()
    cur = conn.cursor()
    rows = cur.execute("SELECT * FROM cibles ORDER BY date_creation DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _campagne_use_cible(conn: sqlite3.Connection, id_cible: str) -> Dict[str, Any] | None:
    """
    Retourne la campagne active (en cours / planifiée) si elle utilise la cible.
    """
    try:
        r = conn.execute(
            """
            SELECT id_campagne, nom_campagne, etat
              FROM campagnes
             WHERE id_cible = ?
               AND (etat = 'En cours' OR etat = 'Planifiée')
             LIMIT 1
            """,
            (id_cible,),
        ).fetchone()
        if not r:
            return None
        return {"id_campagne": r[0], "nom_campagne": r[1], "etat": r[2]}
    except Exception:
        return None


def delete_cible(id_cible: str) -> None:
    """
    Supprime une cible SI elle n'est pas utilisée par une campagne active (En cours/Planifiée).
    - Si source = fichier plat => supprime aussi le fichier du disque
    - ❌ Ne touche PAS aux clients
    """
    ensure_cibles_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Lock : campagne active / planifiée
    used = _campagne_use_cible(conn, id_cible)
    if used:
        conn.close()
        raise ValueError(
            f"Impossible de supprimer: cible utilisée par campagne active/planifiée "
            f"'{used.get('nom_campagne')}' ({used.get('etat')})."
        )

    # Récupérer cible
    cur.execute("SELECT * FROM cibles WHERE id_cible = ?", (id_cible,))
    r = cur.fetchone()
    if not r:
        conn.close()
        return

    source = (r["source"] or "").strip()
    chemin = (r["chemin"] or "").strip()

    # Delete row
    cur.execute("DELETE FROM cibles WHERE id_cible = ?", (id_cible,))
    conn.commit()
    conn.close()

    # Delete file if needed
    if source == "Fichier plat" and chemin and os.path.exists(chemin):
        try:
            os.remove(chemin)
        except Exception:
            pass


def get_cibles_count() -> int:
    ensure_cibles_table()
    conn = _connect()
    cur = conn.cursor()
    r = cur.execute("SELECT COUNT(*) FROM cibles").fetchone()
    conn.close()
    return int(r[0] if r else 0)


def get_cible(id_cible: str) -> Dict[str, Any] | None:
    ensure_cibles_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM cibles WHERE id_cible = ?", (id_cible,))
    r = cur.fetchone()
    conn.close()
    return dict(r) if r else None


def update_cible(cible: Cible) -> None:
    """Met à jour une cible existante (même id_cible).

    IMPORTANT:
    - Ne change pas l'id
    - Respecte la nomenclature existante: source = "DB" | "Fichier plat"
    - Sérialise filtre en JSON uniquement si source == "DB"
    - Stocke chemin uniquement si source == "Fichier plat"
    """
    ensure_cibles_table()
    conn = _connect()
    cur = conn.cursor()

    if not getattr(cible, "id_cible", None) or not str(cible.id_cible).strip():
        conn.close()
        raise ValueError("id_cible obligatoire pour update")

    cible.validate()

    filtre_str = json.dumps(cible.filtre, ensure_ascii=False) if cible.source == "DB" else ""
    chemin = str(cible.chemin or "").strip() if cible.source == "Fichier plat" else ""

    cur.execute(
        """
        UPDATE cibles
           SET nom_cible = ?,
               source    = ?,
               filtre    = ?,
               chemin    = ?
         WHERE id_cible  = ?
        """,
        (
            str(cible.nom_cible).strip(),
            str(cible.source).strip(),
            filtre_str,
            chemin,
            str(cible.id_cible).strip(),
        ),
    )

    conn.commit()
    conn.close()


#======================================
# UPLOAD FILE (Streamlit)
# ======================================
def save_uploaded_file(uploaded_file) -> str:
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    name = uploaded_file.name
    base, ext = os.path.splitext(name)
    dst = os.path.join(UPLOAD_DIR, name)

    # éviter overwrite
    i = 1
    while os.path.exists(dst):
        dst = os.path.join(UPLOAD_DIR, f"{base}_{i}{ext}")
        i += 1

    with open(dst, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return dst


# =========================================================
# IMPORT LEADS -> CLIENTS
# =========================================================
def _read_flat_file(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower().strip(".")
    if ext == "csv":
        return pd.read_csv(path)
    if ext in ("xlsx", "xls"):
        return pd.read_excel(path, sheet_name=0)  # 1ère feuille
    if ext == "parquet":
        return pd.read_parquet(path)
    raise ValueError("Type de fichier non supporté (csv/xlsx/xls/parquet)")


def _detect_clients_table(conn: sqlite3.Connection) -> str:
    """
    Trouve automatiquement la table clients.
    """
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "clients" in tables:
        return "clients"
    for t in tables:
        if t.lower() == "client" or "client" in t.lower():
            return t
    return "clients"


def import_leads_into_clients(file_path: str) -> Tuple[int, int]:
    """
    Import d'un fichier plat (csv/xlsx) vers la table clients.
    - Upsert basé sur Radical_compte (si existe)
    """
    conn = _connect()
    clients_table = _detect_clients_table(conn)

    if file_path.lower().endswith(".csv"):
        df = pd.read_csv(file_path)
    else:
        df = pd.read_excel(file_path)

    df.columns = [str(c).strip() for c in df.columns]

    key_col = "Radical_compte" if "Radical_compte" in df.columns else None
    inserted = 0
    updated = 0

    for _, row in df.iterrows():
        data = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}

        if key_col and data.get(key_col) is not None:
            cur = conn.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {clients_table} WHERE {key_col} = ?", (data[key_col],))
            exists = cur.fetchone()[0] > 0

            if exists:
                cols = [c for c in data.keys() if c != key_col]
                if cols:
                    set_clause = ", ".join([f"{c} = ?" for c in cols])
                    vals = [data[c] for c in cols] + [data[key_col]]
                    cur.execute(
                        f"UPDATE {clients_table} SET {set_clause} WHERE {key_col} = ?",
                        vals,
                    )
                updated += 1
            else:
                cols = list(data.keys())
                ph = ", ".join(["?"] * len(cols))
                cur.execute(
                    f"INSERT INTO {clients_table} ({', '.join(cols)}) VALUES ({ph})",
                    [data[c] for c in cols],
                )
                inserted += 1
            conn.commit()
        else:
            cur = conn.cursor()
            cols = list(data.keys())
            ph = ", ".join(["?"] * len(cols))
            cur.execute(
                f"INSERT INTO {clients_table} ({', '.join(cols)}) VALUES ({ph})",
                [data[c] for c in cols],
            )
            inserted += 1
            conn.commit()

    conn.close()
    return inserted, updated


def get_distinct_values_clients(column: str) -> List[str]:
    """
    Retourne les valeurs distinctes d'une colonne de la table clients (utile pour filtres).
    """
    conn = _connect()
    conn.row_factory = sqlite3.Row
    clients_table = _detect_clients_table(conn)

    try:
        rows = conn.execute(
            f"SELECT DISTINCT {column} AS v FROM {clients_table} WHERE {column} IS NOT NULL ORDER BY {column}"
        ).fetchall()
        return [str(r["v"]) for r in rows if str(r["v"]).strip() != ""]
    except Exception:
        return []
    finally:
        conn.close()


def _query_clients_by_filtre(filtre: Dict[str, Any]) -> pd.DataFrame:
    conn = _connect()
    table = _detect_clients_table(conn)

    where = []
    params = []

    for field, payload in (filtre or {}).items():
        if not isinstance(payload, dict):
            continue

        if "values" in payload:
            vals = payload.get("values") or []
            vals = [str(v) for v in vals if str(v).strip() != ""]
            if vals:
                where.append(f"{field} IN ({', '.join(['?'] * len(vals))})")
                params.extend(vals)
        else:
            if payload.get("min") is not None:
                where.append(f"{field} >= ?")
                params.append(payload["min"])
            if payload.get("max") is not None:
                where.append(f"{field} <= ?")
                params.append(payload["max"])

    sql = f"SELECT * FROM {table}"
    if where:
        sql += " WHERE " + " AND ".join(where)

    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def load_clients_df_for_cible(id_cible: str) -> pd.DataFrame:
    """
    Fonction attendue par campagne_service.
    Retourne la population complète d'une cible sous forme DataFrame.
    """
    cible = get_cible(id_cible)
    if not cible:
        raise ValueError(f"Cible introuvable: {id_cible}")

    source = (cible.get("source") or "").strip()

    if source == "DB":
        filtre = {}
        try:
            filtre_str = cible.get("filtre") or "{}"
            filtre = json.loads(filtre_str) if isinstance(filtre_str, str) else (filtre_str or {})
        except Exception:
            filtre = {}

        df = _query_clients_by_filtre(filtre)

        cols = {c.lower(): c for c in df.columns}
        if "radical_compte" in cols:
            return df.rename(columns={cols["radical_compte"]: "radical_compte"})

        raise ValueError("Base clients: colonne 'radical_compte' manquante")

    if source == "Fichier plat":
        path = (cible.get("chemin") or "").strip()
        if not path:
            raise ValueError("Chemin fichier plat manquant dans la cible")
        df = _read_flat_file(path)

        cols = {c.lower(): c for c in df.columns}
        if "radical_compte" in cols:
            return df.rename(columns={cols["radical_compte"]: "radical_compte"})

        raise ValueError("Fichier plat cible: colonne 'radical_compte' manquante")

    raise ValueError(f"Source cible invalide: {source}")
