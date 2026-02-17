from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional


# =========================================================
# Helpers
# =========================================================

def normalize_variable(variable: str) -> str:
    return (variable or "").strip()


def _validate_conditions_list(conds: Any, label: str) -> None:
    """
    Vérifie qu'un champ de conditions est une liste (de dict en pratique).
    On valide surtout le type "list" ici, sans imposer la structure interne.
    """
    if not isinstance(conds, list):
        raise ValueError(f"{label} doit être une liste")


def _validate_conditions_by_parent(cbp: Any) -> None:
    """
    Vérifie que ConditionsByParent est un dict { parent_id(str/int): list[cond] }.
    """
    if not isinstance(cbp, dict):
        raise ValueError("ConditionsByParent doit être un dict")

    for pid, conds in cbp.items():
        # pid peut être int/str -> on accepte, on normalise juste conceptuellement
        if not isinstance(conds, list):
            raise ValueError(f"ConditionsByParent[{pid}] doit être une liste")

def _safe_parent_ids(parents: Any) -> List[str]:
    if not isinstance(parents, list):
        return []
    return [str(p).strip() for p in parents if str(p).strip()]


def _build_children_map(liste_action: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Retourne { parent_id(str): [child_bloc_dict, ...] }
    """
    children: Dict[str, List[Dict[str, Any]]] = {}
    for b in (liste_action or []):
        bid = str(b.get("ID"))
        for pid in _safe_parent_ids(b.get("Parents")):
            children.setdefault(pid, []).append(b)
    return children


def _validate_objective_operator(op: Any) -> None:
    if op is None:
        return
    if not isinstance(op, str):
        raise ValueError("ObjectiveOperator doit être une string")
    if op.upper() not in {"AND", "OR"}:
        raise ValueError("ObjectiveOperator doit être 'AND' ou 'OR'")


def _validate_valide_objectif_value(v: Any, label: str = "valide_objectif") -> None:
    if v is None:
        return
    if not isinstance(v, str):
        raise ValueError(f"{label} doit être une string")
    if v not in {"Oui", "Non", "no_goal"}:
        raise ValueError(f"{label} doit être 'Oui', 'Non' ou 'no_goal'")


def validate_blocs_schema(liste_action: List[Dict[str, Any]]) -> None:
    """
    Schéma STRICT (avec rétrocompatibilité) + règles objectifs:

    - ObjectiveOperator: 'AND' | 'OR' (optionnel, défaut implicite = AND)
    - Si un bloc a un parent objectif => bloc enfant doit avoir valide_objectif='Oui' ou 'Non'
    - Si aucun parent objectif => valide_objectif doit être 'no_goal' ou absent (on tolère absent pour rétrocompat)
    - Un bloc objectif ne peut avoir que 2 fils max:
        - au plus 1 fils avec valide_objectif='Oui'
        - au plus 1 fils avec valide_objectif='Non'
    """

    # ----- validations bloc par bloc (ton existant) -----
    for b in (liste_action or []):
        if not isinstance(b, dict):
            raise ValueError("Bloc invalide (non dict)")

        if b.get("ID") is None:
            raise ValueError("Bloc sans ID")

        if not isinstance(b.get("Parents"), list):
            raise ValueError("Bloc: 'Parents' doit être une liste")

        if "objectif" not in b:
            raise ValueError("Bloc: clé 'objectif' manquante")

        is_obj = bool(b.get("objectif"))

        conds_global = b.get("Conditions", None)
        cbp = b.get("ConditionsByParent", None)
        obj_conds = b.get("ObjectiveConditions", None)

        # ✅ NEW
        obj_op = b.get("ObjectiveOperator", None)
        _validate_objective_operator(obj_op)

        # ✅ NEW: valide_objectif (valeur brute, cohérence parent gérée plus bas)
        _validate_valide_objectif_value(b.get("valide_objectif", None))

        if conds_global is not None:
            _validate_conditions_list(conds_global, "Conditions")

        if cbp is not None:
            _validate_conditions_by_parent(cbp)

        if obj_conds is not None:
            _validate_conditions_list(obj_conds, "ObjectiveConditions")

        # --- OBJECTIF ---
        if is_obj:
            if b.get("Canal"):
                raise ValueError("Bloc objectif ne doit pas avoir de Canal")
            if b.get("Action"):
                raise ValueError("Bloc objectif ne doit pas avoir d'Action")

            parents = b.get("Parents") or []
            if len(parents) > 0:
                has_entry_conditions = False
                if isinstance(cbp, dict) and len(cbp) > 0:
                    has_entry_conditions = True
                if isinstance(conds_global, list) and len(conds_global) > 0:
                    has_entry_conditions = True
                if not has_entry_conditions:
                    raise ValueError(
                        "Bloc objectif: conditions d'entrée manquantes "
                        "(attendu: ConditionsByParent ou Conditions)"
                    )

            if not isinstance(obj_conds, list) or len(obj_conds) == 0:
                raise ValueError("Bloc objectif doit contenir ObjectiveConditions (liste non vide)")

        # --- NORMAL ---
        else:
            if not b.get("Canal"):
                raise ValueError("Bloc normal: Canal obligatoire")
            if not b.get("Action"):
                raise ValueError("Bloc normal: Action obligatoire")
            if obj_conds is not None:
                raise ValueError("Bloc normal ne doit pas contenir ObjectiveConditions")

    # ----- validations cross-blocs (NEW) -----
    # Map parent->children
    id_to_block: Dict[str, Dict[str, Any]] = {str(b.get("ID")): b for b in (liste_action or [])}
    children_map = _build_children_map(liste_action)

    # (1) Cohérence valide_objectif sur les enfants
    for child in (liste_action or []):
        child_parents = _safe_parent_ids(child.get("Parents"))
        if not child_parents:
            # Racine: no_goal ok (ou absent)
            v = child.get("valide_objectif", None)
            if v is not None and v != "no_goal":
                raise ValueError("Bloc racine: valide_objectif doit être 'no_goal' (ou absent)")
            continue

        has_objective_parent = any(bool(id_to_block.get(pid, {}).get("objectif")) for pid in child_parents)

        v = child.get("valide_objectif", None)

        if has_objective_parent:
            # Recommandation forte: 1 seul parent objectif pour éviter ambiguïté
            obj_parents = [pid for pid in child_parents if bool(id_to_block.get(pid, {}).get("objectif"))]
            if len(obj_parents) != 1:
                raise ValueError(
                    "Un bloc enfant d'objectif doit avoir exactement 1 parent objectif "
                    "(sinon 'valide_objectif' est ambigu)"
                )

            if v not in {"Oui", "Non"}:
                raise ValueError("Bloc enfant d'objectif: valide_objectif doit être 'Oui' ou 'Non'")
        else:
            # Aucun parent objectif
            if v is not None and v != "no_goal":
                raise ValueError("Bloc sans parent objectif: valide_objectif doit être 'no_goal' (ou absent)")

    # (2) Objectif <= 2 fils (Oui/Non)
    for pid, parent in id_to_block.items():
        if not bool(parent.get("objectif")):
            continue

        childs = children_map.get(pid, [])
        # ne garder que ceux qui ont pid comme parent (déjà fait) + vérifier le tag
        oui = [c for c in childs if c.get("valide_objectif") == "Oui"]
        non = [c for c in childs if c.get("valide_objectif") == "Non"]
        other = [c for c in childs if c.get("valide_objectif") not in {"Oui", "Non"}]

        if other:
            raise ValueError(f"Bloc objectif #{pid}: chaque fils doit avoir valide_objectif='Oui' ou 'Non'")

        if len(oui) > 1 or len(non) > 1:
            raise ValueError(f"Bloc objectif #{pid}: un seul fils Oui et un seul fils Non autorisés")

        if len(childs) > 2:
            raise ValueError(f"Bloc objectif #{pid}: maximum 2 fils (Oui/Non)")



# =========================================================
# MODELE
# =========================================================

@dataclass
class Modele:
    id_modele: Optional[str]
    nom_modele: str
    date_creation: str
    liste_action: List[Dict[str, Any]]
    graphe_json: Dict[str, Any]

    # -----------------------------------------------------
    # Constructeur principal
    # -----------------------------------------------------
    @staticmethod
    def new(
        nom_modele: str,
        liste_action: List[Dict[str, Any]],
        graphe_json: Optional[Dict[str, Any]] = None,
    ) -> "Modele":

        if not nom_modele or not nom_modele.strip():
            raise ValueError("Nom du modèle obligatoire")

        # Validation stricte nouvelle structure
        validate_blocs_schema(liste_action)

        dc = date.today().isoformat()

        return Modele(
            id_modele=None,
            nom_modele=nom_modele.strip(),
            date_creation=dc,
            liste_action=liste_action,
            graphe_json=graphe_json or {"nodes": [], "edges": []},
        )

    # -----------------------------------------------------
    # JSON serialization
    # -----------------------------------------------------
    def liste_action_json(self) -> str:
        return json.dumps(self.liste_action, ensure_ascii=False)

    def graphe_json_str(self) -> str:
        return json.dumps(self.graphe_json, ensure_ascii=False)
