from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

import pandas as pd

from app.storage.cibles_store_sqlite import (
    ensure_cibles_table,
    list_cibles,
    get_cible,
    insert_cible,
    update_cible,
    delete_cible,
    save_uploaded_file,
    import_leads_into_clients,
    get_distinct_values_clients,
    load_clients_df_for_cible,
)
from app.storage.campagnes_store_sqlite import list_campagnes_active
from app.domain.cible import Cible


# =========================================================
# JSON helpers (safe)
# =========================================================
def _safe_json_load(s: Any, default):
    if s is None:
        return default
    if isinstance(s, (dict, list)):
        return s
    if not isinstance(s, str):
        return default
    if not s.strip():
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


# =========================================================
# Verrouillage cibles (campagnes actives)
# =========================================================

from app.storage.cibles_store_sqlite import count_clients_for_cible

def get_cible_volume_for_ui(id_cible: str) -> int:
    return int(count_clients_for_cible(id_cible) or 0)


def get_locked_cibles_for_ui() -> Tuple[set[str], Dict[str, str]]:
    """
    Reproduit la logique UI actuelle:
    - locked si une campagne active utilise la cible
    - message "Campagne 'nom' (etat)"
    """
    active_camps = list_campagnes_active() or []
    locked_ids: set[str] = set()
    reasons: Dict[str, str] = {}

    for c in active_camps:
        cid = _safe_str(c.get("id_cible", ""))
        if not cid:
            continue
        locked_ids.add(cid)

        etat = _safe_str(c.get("etat") or c.get("etat_campagne") or "")
        nom = _safe_str(c.get("nom_campagne") or c.get("nom") or "")
        reasons[cid] = f"Campagne '{nom}' ({etat})" if nom or etat else "Liée à une campagne active/planifiée"

    return locked_ids, reasons


# =========================================================
# List / Read
# =========================================================
def list_cibles_for_ui() -> List[Dict[str, Any]]:
    ensure_cibles_table()
    items = list_cibles() or []
    for r in items:
        if isinstance(r, dict) and _safe_str(r.get("source")) == "DB":
            r["filtre"] = _safe_json_load(r.get("filtre") or "{}", {})
        elif isinstance(r, dict):
            r["filtre"] = {}
    return items



def get_cible_for_ui(id_cible: str) -> Dict[str, Any] | None:
    if not id_cible:
        return None
    ensure_cibles_table()
    row = get_cible(id_cible)
    if not isinstance(row, dict):
        return row

    # filtre parsé pour le front
    if _safe_str(row.get("source")) == "DB":
        row["filtre"] = get_cible_filtre_dict_for_ui(row)
    else:
        row["filtre"] = {}

    # ✅ volume
    try:
        row["volume"] = get_cible_volume_for_ui(id_cible)
    except Exception:
        row["volume"] = 0

    return row




def get_cible_filtre_dict_for_ui(cible_row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse le champ 'filtre' (json str) pour une cible DB.
    (Copie fidèle de l'UI actuelle.)
    """
    if not isinstance(cible_row, dict):
        return {}
    filtre_str = cible_row.get("filtre") or "{}"
    filtre = _safe_json_load(filtre_str, {})
    return filtre if isinstance(filtre, dict) else {}


# =========================================================
# Distinct values (pour multiselect)
# =========================================================
def get_distinct_values_for_ui(sql_column: str) -> List[str]:
    """
    Proxy direct vers storage.get_distinct_values_clients
    """
    if not sql_column:
        return []
    return get_distinct_values_clients(sql_column) or []


# =========================================================
# Upload + import
# =========================================================
def save_uploaded_file_for_ui(uploaded_file) -> str:
    return save_uploaded_file(uploaded_file)


def import_leads_into_clients_for_ui(file_path: str) -> Tuple[int, int]:
    return import_leads_into_clients(file_path)


# =========================================================
# CRUD (cibles)
# =========================================================
def create_cible_db_for_ui(nom_cible: str, filtre_dict: Dict[str, Any]) -> str:
    """
    Crée une cible DB à partir du filtre dict déjà construit par l'UI.
    """
    c = Cible(
        id_cible="",
        nom_cible=nom_cible,
        source="DB",
        filtre=filtre_dict if isinstance(filtre_dict, dict) else {},
        chemin="",
    )
    return insert_cible(c)


def create_cible_file_for_ui(nom_cible: str, file_path: str) -> str:
    """
    Crée une cible "Fichier plat" avec chemin.
    """
    c = Cible(
        id_cible="",
        nom_cible=nom_cible,
        source="Fichier plat",
        filtre={},
        chemin=file_path,
    )
    return insert_cible(c)


def update_cible_for_ui(
    id_cible: str,
    nom_cible: str,
    source: str,
    date_creation: str,
    filtre_dict: Dict[str, Any] | None,
    chemin: str,
) -> None:
    cible_obj = Cible(
        id_cible=id_cible,
        nom_cible=nom_cible,
        source=source,
        date_creation=date_creation,
        filtre=filtre_dict if (source == "DB" and isinstance(filtre_dict, dict)) else {},
        chemin=chemin if source != "DB" else "",
    )
    update_cible(cible_obj)


def delete_cible_for_ui(id_cible: str) -> None:
    delete_cible(id_cible)


# =========================================================
# Preview / Visualisation
# =========================================================
def preview_cible_for_ui(id_cible: str, limit: int = 200) -> Tuple[pd.DataFrame, int]:
    """
    Visualise une cible existante, comme ton bouton "👁️ Visualiser".
    - Utilise la même fonction de vérité que campagne_service: load_clients_df_for_cible
    - Retourne (df_head, total_rows)
    """
    if not id_cible:
        raise ValueError("id_cible manquant")

    df = load_clients_df_for_cible(id_cible)  # source DB ou fichier plat (géré dans storage)
    total = int(len(df))
    lim = int(limit) if int(limit) > 0 else 200
    return df.head(lim), total


def preview_file_path_for_ui(path: str, limit: int = 200) -> Tuple[pd.DataFrame, int]:
    """
    Visualiser un fichier plat par chemin (si tu veux preview immédiat).
    (Optionnel, mais safe.)
    """
    if not path or not os.path.exists(path):
        raise ValueError("Fichier introuvable sur le disque.")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(path)
    elif ext in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    elif ext == ".parquet":
        df = pd.read_parquet(path)
    else:
        raise ValueError("Type de fichier non supporté (csv/xlsx/xls/parquet)")
    total = int(len(df))
    lim = int(limit) if int(limit) > 0 else 200
    return df.head(lim), total
