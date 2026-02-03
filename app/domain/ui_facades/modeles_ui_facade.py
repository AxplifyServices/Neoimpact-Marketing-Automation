from __future__ import annotations

import json
import sqlite3
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.storage.db import DB_PATH
from app.domain.modele import (
    Modele,
    list_variables_objectif,
    modalites_for,
    normalize_variable_cible,
    parse_objectif_numeric,
)

from app.storage.modele_store_sqlite import (
    ensure_modeles_table,
    list_modeles,
    insert_modele,
    delete_modele,
    get_modele_by_id,
    update_modele_field,
)

from app.storage.campagnes_store_sqlite import list_campagnes_active


# =========================================================
# Helpers
# =========================================================
def _safe_str(x: Any) -> str:
    return "" if x is None else str(x).strip()


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


def _is_numeric_sqltype(t: str) -> bool:
    tt = (t or "").upper()
    return ("INT" in tt) or ("REAL" in tt) or ("NUM" in tt) or ("DEC" in tt) or ("DOUBLE" in tt) or ("FLOAT" in tt)


# =========================================================
# DB schema helpers (clients)
# =========================================================
def get_clients_columns_with_types_for_ui() -> Dict[str, str]:
    """
    Retourne {col: type} depuis PRAGMA table_info(clients)
    (sorti du front)
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("PRAGMA table_info(clients)").fetchall()
        out: Dict[str, str] = {}
        for r in rows:
            out[str(r["name"])] = str(r["type"] or "")
        return out
    finally:
        conn.close()


def get_variable_choices_for_ui() -> Tuple[List[str], List[str], List[str]]:
    """
    Construit la liste des variables disponibles comme dans l'UI:
    - d'abord variables catégorielles autorisées (positives only)
    - puis colonnes numériques de clients
    Retourne: (variable_choices, categorical_cols_allowed, numeric_cols)
    """
    cols_types = get_clients_columns_with_types_for_ui()
    if not cols_types:
        return [], [], []

    numeric_cols = [c for c, t in cols_types.items() if _is_numeric_sqltype(t)]
    categorical_cols_allowed = list_variables_objectif()  # positives only

    variable_choices: List[str] = []
    seen: Set[str] = set()

    for c in categorical_cols_allowed:
        if c in cols_types and c not in seen:
            variable_choices.append(c)
            seen.add(c)

    for c in sorted(numeric_cols):
        if c not in seen:
            variable_choices.append(c)
            seen.add(c)

    return variable_choices, categorical_cols_allowed, numeric_cols



# =========================================================
# Conditions (clients columns for UI)
# =========================================================
def _norm_colname_for_compare(name: str) -> str:
    """Normalise pour comparer (case-insensitive + underscores)."""
    s = (name or "").strip().lower()
    # garder lettres/chiffres/_ uniquement
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s


# Colonnes à exclure (celles du screen)
_EXCLUDED_CLIENT_COLS_NORM = {
    "radical_compte",
    "nom",
    "prenom",
    "id_client",
    "numero_tel",
    "mail",
    "canal_acquisition",
    "age",
    "qualite",
    "anciennete",
    "region",
    "agence",
    "gestionnaire",
}


def get_client_condition_fields_for_ui() -> List[Dict[str, str]]:
    """
    Retourne les champs utilisables dans les conditions basées sur la table clients,
    en excluant les colonnes du screen.
    Format:
      [{"col": "nb_transaction", "type": "INTEGER", "is_numeric": "1"}, ...]
    """
    cols_types = get_clients_columns_with_types_for_ui()
    out: List[Dict[str, str]] = []

    for col, t in cols_types.items():
        if _norm_colname_for_compare(col) in _EXCLUDED_CLIENT_COLS_NORM:
            continue
        out.append(
            {
                "col": str(col),
                "type": str(t or ""),
                "is_numeric": "1" if _is_numeric_sqltype(t or "") else "0",
            }
        )

    # tri stable: d'abord non-numériques, puis numériques, par nom
    out.sort(key=lambda d: (d.get("is_numeric") != "0", d.get("col", "").lower()))
    return out
def is_categorical_positive_objectif_for_ui(variable_cible: str) -> bool:
    """
    True si variable_cible correspond à une variable catégorielle autorisée (positives only)
    """
    categorical_cols_allowed = set(list_variables_objectif())
    return normalize_variable_cible(variable_cible) in categorical_cols_allowed


# =========================================================
# Objectif helpers (numérique)
# =========================================================
def build_numeric_objectif_json_for_ui(min_txt: str, max_txt: str) -> str:
    """
    Construit le JSON string {"min": ..., "max": ...} (même logique que l'UI initiale),
    en dehors du front.
    """
    mn = None
    mx = None

    if str(min_txt).strip() != "":
        try:
            mn = float(min_txt)
        except Exception:
            raise ValueError("Min doit être un nombre.")
    if str(max_txt).strip() != "":
        try:
            mx = float(max_txt)
        except Exception:
            raise ValueError("Max doit être un nombre.")

    if mn is None and mx is None:
        raise ValueError("Objectif numérique : min et max ne peuvent pas être tous les deux vides.")

    payload: Dict[str, Any] = {}
    if mn is not None:
        payload["min"] = mn
    if mx is not None:
        payload["max"] = mx

    return json.dumps(payload, ensure_ascii=False)


def numeric_objectif_prefill_for_ui(default_obj: Any) -> Tuple[str, str]:
    """
    Préfill min/max à partir d'un objectif stocké (JSON string)
    Retourne (pre_min, pre_max) en string.
    """
    pre_min = ""
    pre_max = ""

    if isinstance(default_obj, str) and default_obj.strip().startswith("{"):
        try:
            mn, mx = parse_objectif_numeric(default_obj)
            pre_min = "" if mn is None else str(mn)
            pre_max = "" if mx is None else str(mx)
        except Exception:
            pass

    return pre_min, pre_max


# =========================================================
# Store proxies (modeles)
# =========================================================
def list_modeles_for_ui() -> List[Dict[str, Any]]:
    ensure_modeles_table()
    return list_modeles() or []


def get_modele_by_id_for_ui(id_modele: str) -> Dict[str, Any]:
    ensure_modeles_table()
    return get_modele_by_id(id_modele) or {}


def get_modele_blocks_for_ui(id_modele: str) -> List[Dict[str, Any]]:
    """
    Retourne liste_action parsée (list[dict]) pour un modèle.
    """
    d = get_modele_by_id_for_ui(id_modele)
    raw = d.get("liste_action") or "[]"
    blocks = _safe_json_load(raw, [])
    return blocks if isinstance(blocks, list) else []


def get_actions_from_row_for_ui(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Utilisé dans la LIST/Détails: parse r.get("liste_action") en list.
    """
    raw = row.get("liste_action") or "[]"
    actions = _safe_json_load(raw, [])
    return actions if isinstance(actions, list) else []


def insert_modele_for_ui(modele: Modele) -> str:
    ensure_modeles_table()
    return insert_modele(modele)


def delete_modele_for_ui(id_modele: str) -> None:
    ensure_modeles_table()
    delete_modele(id_modele)


def save_modele_for_ui(
    *,
    is_editing: bool,
    id_modele: str,
    nom_modele: str,
    variable_cible: str,
    objectif_value_for_store: str,
    blocks: List[Dict[str, Any]],
) -> None:
    """
    Centralise INSERT/UPDATE hors UI, en conservant exactement tes champs et ton store.
    """
    ensure_modeles_table()

    if is_editing:
        mid = _safe_str(id_modele)
        update_modele_field(mid, "nom_modele", nom_modele)
        update_modele_field(mid, "variable_cible", variable_cible)
        update_modele_field(mid, "objectif", objectif_value_for_store)
        update_modele_field(mid, "liste_action", json.dumps(blocks, ensure_ascii=False))
    else:
        modele = Modele.new(
            nom_modele=nom_modele,
            variable_cible=variable_cible,
            objectif=objectif_value_for_store,
            liste_action=blocks,
        )
        insert_modele(modele)


# =========================================================
# Locking (campagnes actives)
# =========================================================
def get_locked_modele_ids_for_ui() -> Set[str]:
    """
    Locked si lié à une campagne active/planifiée.
    """
    active_camps = list_campagnes_active() or []
    locked: Set[str] = set()
    for c in active_camps:
        mid = _safe_str(c.get("id_modele") or c.get("ID_MODELE") or c.get("Id_modele") or "")
        if mid:
            locked.add(mid)
    return locked


# =========================================================
# Edit payload (préfill)
# =========================================================
def get_modele_edit_payload_for_ui(id_modele: str) -> Dict[str, Any]:
    """
    Retourne tout ce qu'il faut pour pré-remplir l'UI en mode édition:
      - nom_modele
      - variable_cible
      - objectif
      - blocks (liste_action parsed)
    """
    d = get_modele_by_id_for_ui(id_modele)

    nom = _safe_str(d.get("nom_modele") or d.get("Nom_modele") or "")
    varc = _safe_str(d.get("variable_cible") or "")
    obj = d.get("objectif", d.get("Objectif"))

    blocks = get_modele_blocks_for_ui(id_modele)

    return {
        "id_modele": _safe_str(id_modele),
        "nom_modele": nom,
        "variable_cible": varc,
        "objectif": obj,
        "blocks": blocks,
    }
