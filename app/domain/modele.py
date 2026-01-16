from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple


# =========================================================
# Modalités "positives" uniquement (objectif atteignable)
# ✅ Clés = colonnes DB (snake_case) pour coller au pattern
# =========================================================
MODALITES_BY_VARIABLE: Dict[str, List[str]] = {
    "STATUT_CLIENT": ["Actif", "Inactif"],
    "Dossier_Complet": ["OUI"],
    "Validation_KYC": ["OUI"],
    "Activation_du_compte": ["OUI"],
    "Activation_carte": ["OUI"],
    "Epargne": ["OUI"],
    "Carte_Actuelle": ["Silver", "Gold", "Standard", "Black"],
    "Assurance_Actuelle": ["Immobilier", "Vie"],
}

# Compat rétro : anciens noms “friendly” -> colonnes DB
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
    """
    Variables catégorielles autorisées (positives seulement).
    (Les variables numériques viennent de la DB côté UI.)
    """
    return [k for k, v in MODALITES_BY_VARIABLE.items() if isinstance(v, list) and len(v) > 0]


def modalites_for(variable_cible: str) -> List[str]:
    v = normalize_variable_cible(variable_cible)
    return MODALITES_BY_VARIABLE.get(v, [])


def is_objectif_valide(variable_cible: str, objectif: str) -> bool:
    v = normalize_variable_cible(variable_cible)
    return objectif in modalites_for(v)


def parse_objectif_numeric(objectif: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Objectif numérique stocké comme JSON string: {"min": 10, "max": 20}
    Retourne (min, max). Lève ValueError si format invalide.
    """
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


def objectif_label(variable_cible: str, objectif: str) -> str:
    """
    Label lisible pour l'affichage (graphe / UI).
    - si objectif est un JSON min/max => formatte
    - sinon => renvoie tel quel
    """
    v = normalize_variable_cible(variable_cible)
    if v in MODALITES_BY_VARIABLE:
        return str(objectif)

    # tenter numeric
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

        # Catégoriel connu
        if v in MODALITES_BY_VARIABLE:
            if not is_objectif_valide(v, objectif):
                raise ValueError(f"Objectif invalide '{objectif}' pour la variable '{v}'")
        else:
            # Numérique (stocké en JSON string)
            # On ne valide pas ici l'existence DB de la colonne (fait côté UI),
            # mais on valide le format objectif si numérique.
            parse_objectif_numeric(objectif)

        dc = date.today().isoformat()
        return Modele(
            id_modele=None,
            nom_modele=nom_modele,
            variable_cible=v,  # ✅ on stocke la version normalisée
            objectif=objectif,
            date_creation=dc,
            liste_action=liste_action or [],
            graphe_json=graphe_json or {"nodes": [], "edges": []},
        )

    def liste_action_json(self) -> str:
        return json.dumps(self.liste_action, ensure_ascii=False)

    def graphe_json_str(self) -> str:
        return json.dumps(self.graphe_json, ensure_ascii=False)
