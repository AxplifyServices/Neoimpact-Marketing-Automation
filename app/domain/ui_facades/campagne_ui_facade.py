from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.storage.campagnes_store_sqlite import list_all_campagnes
from app.storage.cibles_store_sqlite import list_cibles
from app.storage.modele_store_sqlite import load_db as load_modeles_db


# =========================
# Helpers JSON (safe)
# =========================
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
    return "" if x is None else str(x)


# =========================
# Campagnes (UI data)
# =========================
def get_campagnes_affichables_for_ui() -> List[Dict[str, Any]]:
    """
    Retourne uniquement les campagnes affichables dans l'écran Campagnes :
    En cours / Planifiée / En pause.
    (Même logique que ton UI actuelle, juste déplacée ici.)
    """
    camps_all = list_all_campagnes()
    camps: List[Dict[str, Any]] = []
    for c in camps_all:
        etat = c.get("etat_campagne", "") or c.get("etat", "")
        if etat in ("En cours", "Planifiée", "En pause"):
            # ✅ description remonte automatiquement si la colonne existe
            # (on force juste une string pour éviter None côté UI)
            if "description" in c:
                c["description"] = _safe_str(c.get("description"))
            camps.append(c)
    return camps


# =========================
# Choices (UI selects)
# =========================
def get_modele_choices_for_ui() -> Tuple[List[str], Dict[str, str]]:
    """
    Reproduit exactement ton _modele_choices() actuel, mais côté façade.
    """
    df = load_modeles_db()
    if df is None or df.empty:
        return [], {}
    labels: List[str] = []
    mapping: Dict[str, str] = {}
    for _, r in df.iterrows():
        lbl = f"{r['ID_MODELE']} — {r['Nom_modele']}"
        labels.append(lbl)
        mapping[lbl] = r["ID_MODELE"]
    return labels, mapping


def get_cible_choices_for_ui() -> Tuple[List[str], Dict[str, str]]:
    """
    Reproduit exactement ton _cible_choices() actuel, mais côté façade.
    """
    cibles = list_cibles() or []
    labels: List[str] = []
    mapping: Dict[str, str] = {}
    for c in cibles:
        lbl = f"{c['id_cible']} — {c['nom_cible']}"
        labels.append(lbl)
        mapping[lbl] = c["id_cible"]
    return labels, mapping


# =========================
# Modele graph payload (UI)
# =========================
def get_modele_graph_payload_for_ui(id_modele: str) -> Optional[Dict[str, Any]]:
    """
    Remplace le bloc UI :
      dfm = load_modeles_db()
      row = dfm[dfm["ID_MODELE"] == id_modele]
      parse liste_action / graphe_json

    Retourne un payload prêt à afficher côté UI.
    """
    if not id_modele:
        return None

    dfm = load_modeles_db()
    if dfm is None or dfm.empty:
        return None

    row = dfm[dfm["ID_MODELE"] == id_modele]
    if row.empty:
        return None

    r = row.iloc[0].to_dict()

    liste_action = _safe_json_load(r.get("liste_action", ""), [])
    graphe_json = _safe_json_load(r.get("graphe_json", ""), {"nodes": [], "edges": []})

    return {
        "id_modele": id_modele,
        "variable_cible": r.get("variable_cible", "") or "",
        "objectif": r.get("Objectif", "") or "",
        "liste_action": liste_action if isinstance(liste_action, list) else [],
        "graphe_json": graphe_json if isinstance(graphe_json, dict) else {"nodes": [], "edges": []},
    }
