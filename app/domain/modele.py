from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple, Union


MODALITES_BY_VARIABLE: Dict[str, List[str]] = {
    "STATUT_CLIENT": ["Actif", "Inactif"],
    "Dossier_Complet": ["OUI"],
    "Validation_KYC": ["OUI"],
    "Activation_du_compte": ["OUI"],
    "Activation_carte": ["OUI"],
    "Epargne": ["OUI"],
    "Carte_Actuelle": ["Silver", "Gold", "Standard", "Black", "Code 30", "Code 212"],
    "Assurance_Actuelle": ["Immobilier", "Vie"],
    "App_instaled": ["Oui"],
    "Premiere_connex": ["Oui"],
    "Carte_virtuelle": ["Oui"],
    "Dotation_touristique": ["Oui"],
    "Dotation_ecom": ["Oui"],
    "Compte_CIH_Mobile": ["Oui"],
    "Compte_MAD_convertible": ["Oui"],
    "chequier_retire": ["Oui"],
    "chequier_active": ["Oui"],
}

FRIENDLY_TO_DB: Dict[str, str] = {
    "Dossier Complet": "Dossier_Complet",
    "Activation du compte": "Activation_du_compte",
    "Activation carte": "Activation_carte",
    "Carte Actuelle": "Carte_Actuelle",
    "Assurance Actuelle": "Assurance_Actuelle",
}


def normalize_variable_cible(variable_cible: str) -> str:
    v = (variable_cible or "").strip()
    return FRIENDLY_TO_DB.get(v, v)


def list_variables_objectif() -> List[str]:
    return [k for k, v in MODALITES_BY_VARIABLE.items() if isinstance(v, list) and len(v) > 0]


def modalites_for(variable_cible: str) -> List[str]:
    v = normalize_variable_cible(variable_cible)
    return MODALITES_BY_VARIABLE.get(v, [])


def is_objectif_valide(variable_cible: str, objectif: str) -> bool:
    v = normalize_variable_cible(variable_cible)
    return objectif in modalites_for(v)


def parse_objectif_numeric(objectif: str) -> Tuple[Optional[float], Optional[float]]:
    if not isinstance(objectif, str) or not objectif.strip():
        raise ValueError("Objectif numérique vide")

    try:
        obj = json.loads(objectif)
    except Exception:
        raise ValueError("Objectif numérique doit être un JSON valide")

    if not isinstance(obj, dict):
        raise ValueError("Objectif numérique JSON doit être un objet")

    mn = obj.get("min", None)
    mx = obj.get("max", None)

    def _to_float(x):
        if x is None or x == "":
            return None
        try:
            return float(x)
        except Exception:
            raise ValueError("min/max doivent être numériques")

    mn_f = _to_float(mn)
    mx_f = _to_float(mx)

    if mn_f is None and mx_f is None:
        raise ValueError("Objectif numérique: min et max ne peuvent pas être tous les deux vides")

    return mn_f, mx_f


# =========================
# ✅ NEW: multi-objectifs
# =========================
def _try_parse_json(s: str) -> Optional[Any]:
    if not isinstance(s, str):
        return None
    ss = s.strip()
    if not ss:
        return None
    if not (ss.startswith("{") or ss.startswith("[")):
        return None
    try:
        return json.loads(ss)
    except Exception:
        return None


def validate_objectif_expr(expr: Any) -> None:
    """
    Valide un objectif multi sous forme dict:
      {"op":"AND|OR", "items":[ ... ]}
    item cat: {"variable":"Epargne","type":"cat","value":"Oui"}
    item num: {"variable":"NB_appel","type":"num","min":2,"max":5}
    """
    if not isinstance(expr, dict):
        raise ValueError("Objectif multi doit être un objet JSON")

    op = str(expr.get("op", "")).upper().strip()
    if op not in {"AND", "OR"}:
        raise ValueError("Objectif multi: 'op' doit être AND ou OR")

    items = expr.get("items")
    if not isinstance(items, list) or len(items) == 0:
        raise ValueError("Objectif multi: 'items' doit être une liste non vide")

    for it in items:
        if not isinstance(it, dict):
            raise ValueError("Objectif multi: chaque item doit être un objet")

        var = normalize_variable_cible(str(it.get("variable", "")).strip())
        if not var:
            raise ValueError("Objectif multi: variable vide")

        typ = str(it.get("type", "")).lower().strip()
        if typ not in {"cat", "num"}:
            raise ValueError("Objectif multi: type doit être 'cat' ou 'num'")

        if typ == "cat":
            val = str(it.get("value", "")).strip()
            if not val:
                raise ValueError(f"Objectif multi: value vide pour {var}")
            if var in MODALITES_BY_VARIABLE and not is_objectif_valide(var, val):
                raise ValueError(f"Objectif multi invalide '{val}' pour la variable '{var}'")

        if typ == "num":
            # on accepte min/max numériques ou str numériques
            mn = it.get("min", None)
            mx = it.get("max", None)

            def _to_float(x):
                if x is None or x == "":
                    return None
                try:
                    return float(x)
                except Exception:
                    raise ValueError(f"Objectif multi: min/max non numérique pour {var}")

            mn_f = _to_float(mn)
            mx_f = _to_float(mx)
            if mn_f is None and mx_f is None:
                raise ValueError(f"Objectif multi: min et max vides pour {var}")


def objectif_label(variable_cible: str, objectif: str) -> str:
    v = normalize_variable_cible(variable_cible)

    # ✅ Multi-objectif JSON
    expr = _try_parse_json(objectif)
    if isinstance(expr, dict) and "op" in expr and "items" in expr:
        op = str(expr.get("op", "")).upper()
        parts = []
        for it in expr.get("items", []):
            if not isinstance(it, dict):
                continue
            var = normalize_variable_cible(str(it.get("variable", "")))
            typ = str(it.get("type", "")).lower()
            if typ == "cat":
                parts.append(f"{var}={it.get('value')}")
            elif typ == "num":
                mn = it.get("min", None)
                mx = it.get("max", None)
                if mn is not None and mx is not None:
                    parts.append(f"{var}[{mn}..{mx}]")
                elif mn is not None:
                    parts.append(f"{var}>={mn}")
                elif mx is not None:
                    parts.append(f"{var}<={mx}")
        return f" {op} ".join(parts) if parts else objectif

    # Catégoriel connu
    if v in MODALITES_BY_VARIABLE:
        return str(objectif)

    # tenter numeric "legacy" JSON min/max
    try:
        mn, mx = parse_objectif_numeric(objectif)
        if mn is not None and mx is not None:
            return f"[{mn:g} ; {mx:g}]"
        if mn is not None:
            return f">= {mn:g}"
        if mx is not None:
            return f"<= {mx:g}"
    except Exception:
        pass

    return str(objectif)


@dataclass
class Modele:
    id_modele: Optional[str]
    nom_modele: str
    variable_cible: str
    objectif: str
    date_creation: str  # ISO "YYYY-MM-DD"
    liste_action: List[Dict[str, Any]]
    graphe_json: Dict[str, Any]

    @staticmethod
    def new(
        nom_modele: str,
        variable_cible: str,
        objectif: str,
        liste_action: List[Dict[str, Any]],
        graphe_json: Optional[Dict[str, Any]] = None,
    ) -> "Modele":
        v = normalize_variable_cible(variable_cible)

        # ✅ si objectif est un JSON multi (AND/OR), on valide l'expression
        expr = _try_parse_json(objectif)
        if isinstance(expr, dict) and "op" in expr and "items" in expr:
            validate_objectif_expr(expr)
        else:
            # Catégoriel connu
            if v in MODALITES_BY_VARIABLE:
                if not is_objectif_valide(v, objectif):
                    raise ValueError(f"Objectif invalide '{objectif}' pour la variable '{v}'")
            else:
                # Numérique (stocké en JSON string)
                parse_objectif_numeric(objectif)

        dc = date.today().isoformat()
        return Modele(
            id_modele=None,
            nom_modele=nom_modele,
            variable_cible=v,
            objectif=objectif,
            date_creation=dc,
            liste_action=liste_action or [],
            graphe_json=graphe_json or {"nodes": [], "edges": []},
        )

    def liste_action_json(self) -> str:
        return json.dumps(self.liste_action, ensure_ascii=False)

    def graphe_json_str(self) -> str:
        return json.dumps(self.graphe_json, ensure_ascii=False)
