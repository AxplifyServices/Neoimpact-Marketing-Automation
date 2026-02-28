from __future__ import annotations

import json
import sqlite3
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.storage.db import DB_PATH

# ✅ Nouveau Modele (sans objectif, sans variable_cible)
from app.domain.modele import Modele

# ✅ Nouveau store (sans objectif, sans variable_cible)
from app.storage.modele_store_sqlite import (
    ensure_modeles_table,
    list_modeles,
    insert_modele,
    delete_modele,
    get_modele_dict,
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
    ⚠️ Gardé car utile pour l'UI de conditions / choix variables,
    mais plus pour 'objectif modèle'.

    Retourne: (variable_choices, categorical_cols_allowed, numeric_cols)

    Ici, on considère:
    - categorical_cols_allowed = toutes les colonnes non-numériques de clients
    - numeric_cols = colonnes numériques de clients
    - variable_choices = cat puis num
    """
    cols_types = get_clients_columns_with_types_for_ui()
    if not cols_types:
        return [], [], []

    numeric_cols = [c for c, t in cols_types.items() if _is_numeric_sqltype(t)]
    categorical_cols_allowed = [c for c, t in cols_types.items() if not _is_numeric_sqltype(t)]

    variable_choices: List[str] = []
    seen: Set[str] = set()

    for c in sorted(categorical_cols_allowed):
        if c not in seen:
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

    out.sort(key=lambda d: (d.get("is_numeric") != "0", d.get("col", "").lower()))
    return out


def get_clients_campagnes_condition_fields_for_ui() -> List[Dict[str, str]]:
    """
    Champs utilisables dans les conditions basées sur la table clients_campagnes.
    On expose ici uniquement ce dont tu as besoin.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("PRAGMA table_info(clients_campagnes)").fetchall()
        cols_types: Dict[str, str] = {}
        for r in rows:
            cols_types[str(r["name"])] = str(r["type"] or "")

        wanted = [
            "nb_jour_debut_campagne",
        ]

        out: List[Dict[str, str]] = []
        for col in wanted:
            if col not in cols_types:
                continue
            t = cols_types[col]
            out.append(
                {
                    "col": col,
                    "type": t,
                    "is_numeric": "1" if _is_numeric_sqltype(t or "") else "0",
                }
            )

        out.sort(key=lambda d: (d.get("is_numeric") != "0", d.get("col", "").lower()))
        return out
    finally:
        conn.close()


# =========================================================
# Store proxies (modeles)
# =========================================================
def list_modeles_for_ui() -> List[Dict[str, Any]]:
    ensure_modeles_table()
    return list_modeles() or []


def get_modele_by_id_for_ui(id_modele: str) -> Dict[str, Any]:
    ensure_modeles_table()
    return get_modele_dict(id_modele) or {}


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
    blocks: List[Dict[str, Any]],
    ui_positions: Optional[Dict[str, Any]] = None,  # NEW
) -> None:
    """
    Nouvelle logique:
    - plus d'objectif modèle
    - plus de variable_cible
    - un bloc peut être objectif via b["objectif"]=True + Conditions
    """
    ensure_modeles_table()

    # NEW: positions UI (front only)
    ui_positions = ui_positions if isinstance(ui_positions, dict) else {}

    # ✅ Validation métier via Modele.new (sans insertion)
    _ = Modele.new(
        nom_modele=nom_modele,
        liste_action=blocks,
        graphe_json=None,
        ui_positions=ui_positions,  # NEW
    )

    if is_editing:
        mid = _safe_str(id_modele)
        if not mid:
            raise ValueError("id_modele requis en mode édition")

        update_modele_field(mid, "nom_modele", nom_modele)
        update_modele_field(mid, "liste_action", json.dumps(blocks, ensure_ascii=False))
        update_modele_field(mid, "ui_positions", json.dumps(ui_positions, ensure_ascii=False))  # NEW
    else:
        modele = Modele.new(
            nom_modele=nom_modele,
            liste_action=blocks,
            graphe_json=None,
            ui_positions=ui_positions,  # NEW
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
    Nouvelle UI édition:
      - nom_modele
      - blocks (liste_action parsed)
    """
    d = get_modele_by_id_for_ui(id_modele)

    nom = _safe_str(d.get("nom_modele") or d.get("Nom_modele") or "")
    blocks = get_modele_blocks_for_ui(id_modele)

    ui_positions = _safe_json_load(d.get("ui_positions"), {})
    if not isinstance(ui_positions, dict):
        ui_positions = {}

    return {
        "id_modele": _safe_str(id_modele),
        "nom_modele": nom,
        "blocks": blocks,
        "ui_positions": ui_positions,  # NEW
    }

# =========================================================
# Compat API (objectif multi)
# =========================================================
def build_multi_objectif_json_for_ui(op: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Utilisé par l'endpoint API /meta/objectif/build-multi.
    On retourne une structure simple et stable.
    """
    op2 = (op or "").upper().strip()
    if op2 not in ("AND", "OR"):
        op2 = "AND"

    if not isinstance(items, list):
        items = []

    return {
        "op": op2,
        "items": items,
    }
