from __future__ import annotations

import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple

import pandas as pd
import time

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

def count_clients_for_cible(id_cible: str) -> int:
    cible = get_cible(id_cible)
    if not cible:
        return 0

    source = (cible.get("source") or "").strip()

    # --- DB: COUNT via SQL ---
    if source == "DB":
        filtre = {}
        try:
            filtre_str = cible.get("filtre") or "{}"
            filtre = json.loads(filtre_str) if isinstance(filtre_str, str) else (filtre_str or {})
        except Exception:
            filtre = {}

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

        sql = f"SELECT COUNT(*) as n FROM {table}"
        if where:
            sql += " WHERE " + " AND ".join(where)

        try:
            r = conn.execute(sql, params).fetchone()
            return int(r[0] if r else 0)
        finally:
            conn.close()

    # --- Fichier plat: fallback simple ---
    if source == "Fichier plat":
        path = (cible.get("chemin") or "").strip()
        if not path:
            return 0
        df = _read_flat_file(path)
        return int(len(df))

    return 0

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
    """Met à jour une cible existante (même id_cible)."""
    ensure_cibles_table()
    conn = _connect()
    cur = conn.cursor()

    cible.validate()

    filtre_str = json.dumps(cible.filtre, ensure_ascii=False) if cible.source == "DB" else ""
    chemin = cible.chemin if cible.source == "Fichier plat" else ""

    cur.execute(
        """
        UPDATE cibles
           SET nom_cible = ?,
               date_creation = ?,
               source = ?,
               filtre = ?,
               chemin = ?
         WHERE id_cible = ?
        """,
        (
            cible.nom_cible,
            cible.date_creation,
            cible.source,
            filtre_str,
            chemin,
            cible.id_cible,
        ),
    )
    conn.commit()
    conn.close()


def update_nom_cible(id_cible: str, nom_cible: str) -> None:
    ensure_cibles_table()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE cibles SET nom_cible = ? WHERE id_cible = ?",
        (nom_cible, id_cible),
    )
    conn.commit()
    conn.close()


def update_cible_chemin(id_cible: str, chemin: str) -> None:
    ensure_cibles_table()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE cibles SET chemin = ? WHERE id_cible = ?",
        (chemin, id_cible),
    )
    conn.commit()
    conn.close()


#======================================
# UPLOAD FILE (Streamlit & FastAPI)
# ======================================
def save_uploaded_file(uploaded_file) -> str:
    """
    Save an uploaded file to disk and return the destination path.

    This helper handles both Streamlit ``UploadedFile`` objects and FastAPI ``UploadFile``
    instances. Streamlit expose ``name`` et ``getbuffer``, FastAPI expose
    ``filename`` et ``file`` (file-like).
    """
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Déterminer le nom d'origine : Streamlit -> name ; FastAPI -> filename
    name = getattr(uploaded_file, "name", None) or getattr(uploaded_file, "filename", None)
    if not name:
        # Fallback si aucun nom n'est fourni
        name = f"uploaded_file_{int(time.time())}"

    base, ext = os.path.splitext(name)
    dst = os.path.join(UPLOAD_DIR, name)

    # Éviter d'écraser un fichier existant en suffixant un compteur
    i = 1
    while os.path.exists(dst):
        dst = os.path.join(UPLOAD_DIR, f"{base}_{i}{ext}")
        i += 1

    # Écriture du contenu
    with open(dst, "wb") as f:
        # Streamlit : getbuffer()
        if hasattr(uploaded_file, "getbuffer"):
            f.write(uploaded_file.getbuffer())
        # FastAPI : .file (SpooledTemporaryFile)
        elif hasattr(uploaded_file, "file"):
            uploaded_file.file.seek(0)
            import shutil
            shutil.copyfileobj(uploaded_file.file, f)
        else:
            data = uploaded_file.read() if hasattr(uploaded_file, "read") else None
            if data:
                f.write(data)
            else:
                raise AttributeError("Impossible de lire le fichier envoyé.")
    return dst


# =========================================================
# IMPORT LEADS -> CLIENTS (STRICT)
# =========================================================
STRICT_REQUIRED_COLS = ["ID_Client", "Numero_Tel", "Mail"]
STRICT_KEY_COL = "ID_Client"
RADICAL_COL = "radical_compte"


def _read_flat_file(path: str) -> pd.DataFrame:
    """Lecture multi-formats (CSV, XLSX, Parquet, JSON)."""
    ext = os.path.splitext(path)[1].lower().strip(".")
    if ext == "csv":
        return pd.read_csv(path)
    if ext in ("xlsx", "xls"):
        return pd.read_excel(path, sheet_name=0)
    if ext == "parquet":
        return pd.read_parquet(path)
    if ext == "json":
        return pd.read_json(path)
    raise ValueError("Type de fichier non supporté (csv/xlsx/xls/parquet/json)")


def _detect_clients_table(conn: sqlite3.Connection) -> str:
    """Trouve automatiquement la table clients."""
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "clients" in tables:
        return "clients"
    for t in tables:
        if t.lower() == "client" or "client" in t.lower():
            return t
    return "clients"


def _get_table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def _strict_validate_dataframe_against_clients(df: pd.DataFrame, clients_cols: List[str]) -> None:
    """
    STRICT :
    - Le fichier doit contenir EXACTEMENT les mêmes colonnes que la table clients.
    - Colonnes indispensables (ID_Client, Numero_Tel, Mail) présentes et non nulles.
    """
    df_cols = [str(c).strip() for c in df.columns]
    clients_cols = [str(c).strip() for c in clients_cols]

    df_set = set(df_cols)
    db_set = set(clients_cols)

    missing = sorted(list(db_set - df_set))
    extra = sorted(list(df_set - db_set))

    if missing or extra:
        msg = ["Fichier invalide (STRICT). Le schéma doit correspondre EXACTEMENT à la table clients."]
        if missing:
            msg.append(f"Colonnes manquantes ({len(missing)}) : {', '.join(missing)}")
        if extra:
            msg.append(f"Colonnes en trop ({len(extra)}) : {', '.join(extra)}")
        raise ValueError("\n".join(msg))

    # colonnes indispensables non nulles
    for col in STRICT_REQUIRED_COLS:
        if col not in df_set:
            raise ValueError(f"Fichier invalide : colonne obligatoire manquante : {col}")
        if df[col].isna().any():
            raise ValueError(f"Fichier invalide : la colonne '{col}' contient des valeurs vides (obligatoire).")


def _new_radical_compte(conn: sqlite3.Connection, clients_table: str) -> str:
    """Génère un radical_compte unique. Format : RC000001, RC000002, ..."""
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT {RADICAL_COL} FROM {clients_table} ORDER BY {RADICAL_COL} DESC LIMIT 1")
        r = cur.fetchone()
    except Exception:
        r = None

    if not r or not r[0]:
        return "RC000001"

    last = str(r[0])
    m = re.search(r"(\d+)$", last)
    n = int(m.group(1)) if m else 0
    return f"RC{n+1:06d}"


def import_leads_into_clients(file_path: str) -> Tuple[int, int]:
    """
    STRICT IMPORT vers clients :
    - Schéma identique à la table clients (voir _strict_validate_dataframe_against_clients).
    - Upsert basé sur ID_Client :
      * si ID_Client existe ⇒ UPDATE (ne touche pas radical_compte)
      * sinon ⇒ INSERT + génération radical_compte
    - Colonnes indispensables non nulles : ID_Client, Numero_Tel, Mail
    """
    conn = _connect()
    clients_table = _detect_clients_table(conn)

    df = _read_flat_file(file_path)
    df.columns = [str(c).strip() for c in df.columns]

    # Schéma strict
    clients_cols = _get_table_columns(conn, clients_table)
    _strict_validate_dataframe_against_clients(df, clients_cols)

    inserted = 0
    updated = 0
    cur = conn.cursor()

    for _, row in df.iterrows():
        data = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}

        key_val = data.get(STRICT_KEY_COL)
        if key_val is None or str(key_val).strip() == "":
            raise ValueError("Fichier invalide : ID_Client vide détecté.")

        cur.execute(f"SELECT COUNT(*) FROM {clients_table} WHERE {STRICT_KEY_COL} = ?", (key_val,))
        exists = cur.fetchone()[0] > 0

        if exists:
            # UPDATE : toutes colonnes sauf radical_compte et clé
            cols_to_update = [c for c in clients_cols if c not in (RADICAL_COL, STRICT_KEY_COL)]
            set_clause = ", ".join([f"{c} = ?" for c in cols_to_update])
            vals = [data.get(c) for c in cols_to_update] + [key_val]
            cur.execute(
                f"UPDATE {clients_table} SET {set_clause} WHERE {STRICT_KEY_COL} = ?",
                vals,
            )
            updated += 1
        else:
            # INSERT : on force radical_compte si vide ou non fourni
            if data.get(RADICAL_COL) is None or str(data.get(RADICAL_COL)).strip() == "":
                data[RADICAL_COL] = _new_radical_compte(conn, clients_table)

            cols_insert = clients_cols[:]  # respect de l'ordre DB
            placeholders = ", ".join(["?"] * len(cols_insert))
            cur.execute(
                f"INSERT INTO {clients_table} ({', '.join(cols_insert)}) VALUES ({placeholders})",
                [data.get(c) for c in cols_insert],
            )
            inserted += 1

    conn.commit()
    conn.close()
    return inserted, updated


def get_distinct_values_clients(column: str) -> List[str]:
    """Retourne les valeurs distinctes d'une colonne de la table clients (utile pour filtres)."""
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
    Fonction attendue par campagne_service : retourne la population complète d'une cible sous forme DataFrame.
    """
    cible = get_cible(id_cible)
    if not cible:
        raise ValueError(f"Cible introuvable : {id_cible}")

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
        raise ValueError("Base clients : colonne 'radical_compte' manquante")

    if source == "Fichier plat":
        path = (cible.get("chemin") or "").strip()
        if not path:
            raise ValueError("Chemin fichier plat manquant dans la cible")
        df = _read_flat_file(path)
        cols = {c.lower(): c for c in df.columns}
        if "radical_compte" in cols:
            return df.rename(columns={cols["radical_compte"]: "radical_compte"})
        raise ValueError("Fichier plat cible : colonne 'radical_compte' manquante")

    raise ValueError(f"Source cible invalide : {source}")
