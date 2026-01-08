from __future__ import annotations

import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple

import pandas as pd

from app.domain.cible import Cible

# =========================================================
# CONFIG — DB UNIQUE (NE CHANGE JAMAIS)
# =========================================================
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "clients.db")

# Uploads cibles (fichiers plats)
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "app", "data", "uploads_cibles")


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


# =========================================================
# TABLE CIBLES
# =========================================================
CREATE_CIBLES_SQL = """
CREATE TABLE IF NOT EXISTS cibles (
    id_cible TEXT PRIMARY KEY,
    nom_cible TEXT NOT NULL,
    date_creation TEXT,
    source TEXT,     -- "DB" | "Fichier plat"
    filtre TEXT,     -- JSON string (si DB)
    chemin TEXT      -- chemin fichier (si fichier plat)
);
"""


def ensure_cibles_table() -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(CREATE_CIBLES_SQL)
    conn.commit()
    conn.close()


# =========================================================
# CRUD CIBLES
# =========================================================
def _new_id_cible(cur: sqlite3.Cursor) -> str:
    cur.execute("SELECT COUNT(*) FROM cibles")
    n = cur.fetchone()[0] or 0
    return f"C{n+1:06d}"


def insert_cible(cible: Cible) -> str:
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
        (
            cible.id_cible,
            cible.nom_cible.strip(),
            cible.date_creation,
            cible.source,
            filtre_str,
            chemin,
        ),
    )

    conn.commit()
    conn.close()
    return cible.id_cible


def list_cibles() -> List[Dict[str, Any]]:
    ensure_cibles_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT id_cible, nom_cible, date_creation, source, filtre, chemin "
        "FROM cibles ORDER BY date_creation DESC"
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def _cible_locked_by_active_campaign(cur: sqlite3.Cursor, id_cible: str) -> Dict[str, Any] | None:
    """
    Retourne la campagne active (En cours/Planifiée) qui utilise cette cible, sinon None.
    """
    from app.storage.campagnes_store_sqlite import ensure_table

    ensure_table()
    cur.execute(
        """
        SELECT id_campagne, nom_campagne, etat_campagne
        FROM campagnes
        WHERE id_cible = ?
          AND etat_campagne IN ('En cours', 'Planifiée')
        LIMIT 1
        """,
        (id_cible,),
    )
    r = cur.fetchone()
    if not r:
        return None
    try:
        return dict(r)  # sqlite3.Row
    except Exception:
        return {"id_campagne": r[0], "nom_campagne": r[1], "etat_campagne": r[2]}


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

    # ✅ verrou suppression
    lock = _cible_locked_by_active_campaign(cur, id_cible)
    if lock:
        conn.close()
        raise RuntimeError(
            f"Suppression impossible: la cible {id_cible} est utilisée par la campagne "
            f"{lock.get('id_campagne')} ({lock.get('etat_campagne')})"
        )

    cur.execute("SELECT source, chemin FROM cibles WHERE id_cible = ?", (id_cible,))
    row = cur.fetchone()

    if row and (row["source"] or "").strip() == "Fichier plat":
        path = (row["chemin"] or "").strip()
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

    cur.execute("DELETE FROM cibles WHERE id_cible = ?", (id_cible,))
    conn.commit()
    conn.close()


def get_cible(id_cible: str) -> Dict[str, Any] | None:
    ensure_cibles_table()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM cibles WHERE id_cible = ?", (id_cible,))
    r = cur.fetchone()
    conn.close()
    return dict(r) if r else None


# =========================================================
# UPLOAD FILE (Streamlit)
# =========================================================
def save_uploaded_file(uploaded_file) -> str:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = uploaded_file.name.replace("\\", "_").replace("/", "_")
    dst = os.path.join(UPLOAD_DIR, filename)
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
    if ext == "json":
        return pd.read_json(path)
    if ext == "parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Format non supporté: .{ext}")


def _table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def _get_table_cols(cur: sqlite3.Cursor, table: str) -> List[str]:
    cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def _pick_col(cols: List[str], candidates: List[str]) -> str | None:
    low = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in low:
            return low[cand.lower()]
    return None


def _next_rc(cur: sqlite3.Cursor, col_radical: str) -> str:
    cur.execute(f"SELECT {col_radical} FROM clients WHERE {col_radical} IS NOT NULL")
    maxi = 0
    for (v,) in cur.fetchall():
        if not v:
            continue
        m = re.search(r"(\d+)$", str(v))
        if m:
            maxi = max(maxi, int(m.group(1)))
    return f"RC{maxi+1:08d}"


def import_leads_into_clients(file_path: str) -> Tuple[int, int]:
    df = _read_flat_file(file_path)

    if "id_client" not in df.columns:
        raise ValueError("Colonne obligatoire manquante dans le fichier: id_client")

    df["id_client"] = df["id_client"].astype(str).str.strip()

    conn = _connect()
    cur = conn.cursor()

    if not _table_exists(cur, "clients"):
        conn.close()
        raise RuntimeError("La table 'clients' n'existe pas dans la DB.")

    cols = _get_table_cols(cur, "clients")

    col_id = _pick_col(cols, ["ID_Client", "id_client"])
    col_radical = _pick_col(cols, ["radical_compte", "Radical_compte", "radical compte", "Radical compte"])
    col_statut = _pick_col(cols, ["STATUT_CLIENT", "statut_client", "Statut client"])
    col_tel = _pick_col(cols, ["Numero Tel", "Numero_Tel", "NumeroTel", "Telephone", "Tel", "Mobile"])
    col_mail = _pick_col(cols, ["Mail", "Email", "E-mail"])

    if not col_id or not col_radical or not col_statut:
        conn.close()
        raise RuntimeError(f"Colonnes indispensables manquantes dans clients: {col_id=}, {col_radical=}, {col_statut=}")

    tel_alias = ["Numero Tel", "Numero_Tel", "NumeroTel", "Telephone", "Tel", "Mobile"]
    mail_alias = ["Mail", "Email", "E-mail"]

    added = 0
    skipped = 0

    for _, r in df.iterrows():
        id_client = str(r.get("id_client", "")).strip()
        if not id_client:
            continue

        cur.execute(f"SELECT 1 FROM clients WHERE {col_id} = ?", (id_client,))
        if cur.fetchone():
            skipped += 1
            continue

        radical = _next_rc(cur, col_radical)

        tel_val = ""
        mail_val = ""

        for c in tel_alias:
            if c in df.columns:
                v = r.get(c)
                tel_val = "" if pd.isna(v) else str(v).strip()
                break

        for c in mail_alias:
            if c in df.columns:
                v = r.get(c)
                mail_val = "" if pd.isna(v) else str(v).strip()
                break

        insert_cols = [col_radical, col_id, col_statut]
        insert_vals = [radical, id_client, "Prospect"]

        if col_tel:
            insert_cols.append(col_tel)
            insert_vals.append(tel_val)

        if col_mail:
            insert_cols.append(col_mail)
            insert_vals.append(mail_val)

        placeholders = ",".join(["?"] * len(insert_cols))
        sql = f"INSERT INTO clients ({','.join(insert_cols)}) VALUES ({placeholders})"
        cur.execute(sql, tuple(insert_vals))
        added += 1

    conn.commit()
    conn.close()
    return added, skipped


# =========================================================
# Valeurs distinctes (UI filtres)
# =========================================================
def get_distinct_values_clients(col_name: str) -> List[str]:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT DISTINCT {col_name}
            FROM clients
            WHERE {col_name} IS NOT NULL
              AND TRIM({col_name}) != ''
            ORDER BY {col_name}
            """
        )
        values = [str(r[0]) for r in cur.fetchall()]
    except Exception:
        values = []
    finally:
        conn.close()
    return values


# =========================================================
# UTILITAIRES CAMPAGNES : load_clients_df_for_cible (✅ RESTAURÉ)
# =========================================================
QUALITATIVE_FIELD_TO_COLUMN = {
    "Statut client": "STATUT_CLIENT",
    "Qualité": "Qualite",
    "Région": "Region",
    "Agence": "Agence",
    "Segment actuel": "Segment_actuel",
    "Dossier Complet": "Dossier_Complet",
    "Validation KYC": "Validation_KYC",
    "Activation du compte": "Activation_du_compte",
    "Activation carte": "Activation_carte",
    "Canal d'acquisition": "Canal_acquisition",
    "Epargne": "Epargne",
    "Carte Actuelle": "Carte_Actuelle",
    "Assurance Actuelle": "Assurance_Actuelle",
}

NUM_FIELD_TO_COLUMN = {
    "Age": "Age",
    "Ancienneté": "Anciennete",
}

NUM_FIELDS = ["Age", "Ancienneté"]
CAT_FIELDS = list(QUALITATIVE_FIELD_TO_COLUMN.keys())


def _query_clients_full_by_filtre(filtre_dict: dict) -> pd.DataFrame:
    where = []
    params = []

    for k, v in (filtre_dict or {}).items():
        if k in NUM_FIELDS and isinstance(v, dict):
            col = NUM_FIELD_TO_COLUMN.get(k)
            if not col:
                continue
            minv = v.get("min", None)
            maxv = v.get("max", None)
            if minv is not None:
                where.append(f"{col} >= ?")
                params.append(int(minv))
            if maxv is not None:
                where.append(f"{col} <= ?")
                params.append(int(maxv))

    for k, v in (filtre_dict or {}).items():
        if k in CAT_FIELDS and isinstance(v, dict):
            col = QUALITATIVE_FIELD_TO_COLUMN.get(k)
            if not col:
                continue
            values = v.get("values", [])
            if values:
                placeholders = ",".join(["?"] * len(values))
                where.append(f"{col} IN ({placeholders})")
                params.extend(values)

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    sql = f"SELECT * FROM clients{where_sql}"

    conn = sqlite3.connect(DB_PATH)
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
        filtre_str = (cible.get("filtre") or "").strip()
        filtre = json.loads(filtre_str) if filtre_str else {}
        return _query_clients_full_by_filtre(filtre)

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
