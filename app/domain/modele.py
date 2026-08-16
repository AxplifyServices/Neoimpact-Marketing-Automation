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


def _norm_id(value: Any) -> str:
    """Normalise un identifiant de bloc/parent sans modifier sa valeur métier."""
    return "" if value is None else str(value).strip()


_ALLOWED_CONDITION_OPERATORS = {
    "=",
    "==",
    "!=",
    "<>",
    ">",
    "<",
    ">=",
    "<=",
    "contains",
    "in",
}


def _condition_parts(cond: Dict[str, Any]) -> tuple[str, str, Any, bool]:
    """
    Lit une condition dans les deux formats supportés :

    Nouveau :
        {field, op, value}

    Legacy :
        {Colonne, Operateur, Valeur}

    Retourne :
        (field, operator, value, value_is_present)
    """
    field = str(
        cond.get("field")
        if cond.get("field") is not None
        else cond.get("Colonne") or ""
    ).strip()

    op_raw = (
        cond.get("op")
        if cond.get("op") is not None
        else cond.get("Operateur")
    )
    op = str(op_raw or "=").strip()
    if op.lower() in {"contains", "in"}:
        op = op.lower()

    if "value" in cond:
        value = cond.get("value")
        value_present = True
    elif "Valeur" in cond:
        value = cond.get("Valeur")
        value_present = True
    else:
        value = None
        value_present = False

    return field, op, value, value_present


def _validate_single_condition(cond: Any, label: str) -> None:
    """
    Une condition invalide ne doit jamais devenir implicitement vraie.

    On contrôle ici la structure. La valeur du champ lui-même reste dynamique
    et sera résolue au moment de l'exécution du workflow.
    """
    if not isinstance(cond, dict):
        raise ValueError(f"{label}: chaque condition doit être un objet")

    field, op, value, value_present = _condition_parts(cond)

    if not field:
        raise ValueError(f"{label}: champ/field obligatoire")

    if op not in _ALLOWED_CONDITION_OPERATORS:
        raise ValueError(
            f"{label}: opérateur invalide '{op}'. "
            f"Opérateurs autorisés: {', '.join(sorted(_ALLOWED_CONDITION_OPERATORS))}"
        )

    if not value_present:
        raise ValueError(f"{label}: valeur/value obligatoire")

    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{label}: valeur/value ne peut pas être vide")

    if op in {">", "<", ">=", "<="}:
        try:
            float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{label}: l'opérateur '{op}' exige une valeur numérique"
            ) from exc

    if op == "in":
        if isinstance(value, list):
            if not value:
                raise ValueError(f"{label}: 'in' exige une liste non vide")
        elif not isinstance(value, str):
            raise ValueError(
                f"{label}: 'in' exige une liste ou une chaîne non vide"
            )


def _validate_conditions_list(conds: Any, label: str) -> None:
    """
    Valide une liste de conditions et chacune de ses entrées.
    Une liste vide reste autorisée sauf quand le métier impose explicitement
    au moins une condition (ObjectiveConditions notamment).
    """
    if not isinstance(conds, list):
        raise ValueError(f"{label} doit être une liste")

    for index, cond in enumerate(conds):
        _validate_single_condition(cond, f"{label}[{index}]")


def _validate_conditions_by_parent(
    cbp: Any,
    *,
    block_id: str,
    parent_ids: List[str],
) -> None:
    """
    ConditionsByParent doit être :
        {parent_id: [conditions...]}

    Chaque clé doit correspondre à un parent réel du bloc. Cela fonctionne
    aussi pour une auto-boucle : le propre ID du bloc peut être un parent.
    """
    if not isinstance(cbp, dict):
        raise ValueError(
            f"Bloc #{block_id}: ConditionsByParent doit être un dict"
        )

    allowed_parents = set(parent_ids)

    for raw_pid, conds in cbp.items():
        pid = _norm_id(raw_pid)

        if not pid:
            raise ValueError(
                f"Bloc #{block_id}: ConditionsByParent contient un parent vide"
            )

        if pid not in allowed_parents:
            raise ValueError(
                f"Bloc #{block_id}: ConditionsByParent référence le parent "
                f"'{pid}', absent de Parents"
            )

        _validate_conditions_list(
            conds,
            f"Bloc #{block_id}: ConditionsByParent[{pid}]",
        )


def _safe_parent_ids(parents: Any) -> List[str]:
    if not isinstance(parents, list):
        return []
    return [
        _norm_id(parent)
        for parent in parents
        if _norm_id(parent)
    ]


def _build_children_map(
    liste_action: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Retourne {parent_id: [enfants...]}.

    Les cycles, retours vers des ancêtres et auto-boucles sont volontairement
    conservés : ils font partie du modèle métier.
    """
    children: Dict[str, List[Dict[str, Any]]] = {}

    for bloc in liste_action or []:
        for parent_id in _safe_parent_ids(bloc.get("Parents")):
            children.setdefault(parent_id, []).append(bloc)

    return children


def _validate_objective_operator(op: Any) -> None:
    if op is None:
        return
    if not isinstance(op, str):
        raise ValueError("ObjectiveOperator doit être une string")
    if op.upper() not in {"AND", "OR"}:
        raise ValueError("ObjectiveOperator doit être 'AND' ou 'OR'")


def _validate_valide_objectif_value(
    value: Any,
    label: str = "valide_objectif",
) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ValueError(f"{label} doit être une string")
    if value not in {"Oui", "Non", "no_goal"}:
        raise ValueError(
            f"{label} doit être 'Oui', 'Non' ou 'no_goal'"
        )


def _validate_reachability(
    *,
    root_id: str,
    all_ids: set[str],
    children_map: Dict[str, List[Dict[str, Any]]],
) -> None:
    """
    Tous les blocs doivent être atteignables depuis l'unique racine.

    Cette vérification n'interdit AUCUN cycle :
    - A -> B -> A
    - A -> B -> C -> A
    - B -> B

    Le set `visited` sert uniquement à terminer le contrôle de structure.
    """
    visited: set[str] = set()
    stack: List[str] = [root_id]

    while stack:
        current_id = stack.pop()

        if current_id in visited:
            continue

        visited.add(current_id)

        for child in children_map.get(current_id, []):
            child_id = _norm_id(child.get("ID"))
            if child_id and child_id not in visited:
                stack.append(child_id)

    unreachable = sorted(all_ids - visited)

    if unreachable:
        raise ValueError(
            "Blocs inaccessibles depuis la racine : "
            + ", ".join(unreachable)
        )


def validate_blocs_schema(
    liste_action: List[Dict[str, Any]],
) -> None:
    """
    Valide la structure du graphe de workflow.

    Règles structurelles :
    - liste_action doit contenir au moins un bloc ;
    - chaque bloc possède un ID non vide et UNIQUE ;
    - Parents est toujours une liste ;
    - plusieurs parents sont autorisés ;
    - un parent peut être un ancien ancêtre ;
    - un bloc peut être son propre parent ;
    - chaque référence de parent doit correspondre à un bloc existant ;
    - un même parent ne peut pas être répété deux fois dans Parents ;
    - exactement une racine (Parents == []) ;
    - tous les blocs doivent être atteignables depuis cette racine ;
    - les cycles de toute longueur sont autorisés.

    Conditions :
    - Conditions, ConditionsByParent et ObjectiveConditions sont validés ;
    - une condition mal formée est refusée à l'enregistrement ;
    - une clé ConditionsByParent doit être un parent réel du bloc.

    Objectifs :
    - ObjectiveOperator = AND | OR ;
    - un enfant ayant au moins un parent objectif doit avoir
      valide_objectif = Oui | Non ;
    - plusieurs parents objectifs sont autorisés. La valeur scalaire
      valide_objectif s'applique alors de la même façon à chacun d'eux ;
    - aucune limite sur le nombre de fils Oui/Non d'un objectif.
    """
    if not isinstance(liste_action, list) or not liste_action:
        raise ValueError("Le modèle doit contenir au moins un bloc")

    normalized_blocks: List[Dict[str, Any]] = []
    ids_seen: set[str] = set()

    # -----------------------------------------------------
    # 1. Validation bloc par bloc + unicité des IDs
    # -----------------------------------------------------
    for index, bloc in enumerate(liste_action):
        if not isinstance(bloc, dict):
            raise ValueError(
                f"Bloc #{index + 1}: bloc invalide (non dict)"
            )

        block_id = _norm_id(bloc.get("ID"))

        if not block_id:
            raise ValueError(
                f"Bloc #{index + 1}: ID obligatoire"
            )

        if block_id in ids_seen:
            raise ValueError(
                f"ID de bloc dupliqué : '{block_id}'"
            )

        ids_seen.add(block_id)
        normalized_blocks.append(bloc)

        parents_raw = bloc.get("Parents")

        if not isinstance(parents_raw, list):
            raise ValueError(
                f"Bloc #{block_id}: 'Parents' doit être une liste"
            )

        parent_ids = _safe_parent_ids(parents_raw)

        if len(parent_ids) != len(parents_raw):
            raise ValueError(
                f"Bloc #{block_id}: Parents contient un identifiant vide"
            )

        if len(parent_ids) != len(set(parent_ids)):
            raise ValueError(
                f"Bloc #{block_id}: un même parent est présent plusieurs fois"
            )

        if "objectif" not in bloc:
            raise ValueError(
                f"Bloc #{block_id}: clé 'objectif' manquante"
            )

        if not isinstance(bloc.get("objectif"), bool):
            raise ValueError(
                f"Bloc #{block_id}: 'objectif' doit être un booléen true/false"
            )

        is_objective = bloc.get("objectif") is True

        conditions = bloc.get("Conditions", None)
        conditions_by_parent = bloc.get(
            "ConditionsByParent",
            None,
        )
        objective_conditions = bloc.get(
            "ObjectiveConditions",
            None,
        )

        _validate_objective_operator(
            bloc.get("ObjectiveOperator", None)
        )

        _validate_valide_objectif_value(
            bloc.get("valide_objectif", None),
            f"Bloc #{block_id}: valide_objectif",
        )

        if conditions is not None:
            _validate_conditions_list(
                conditions,
                f"Bloc #{block_id}: Conditions",
            )

        if conditions_by_parent is not None:
            _validate_conditions_by_parent(
                conditions_by_parent,
                block_id=block_id,
                parent_ids=parent_ids,
            )

        if objective_conditions is not None:
            _validate_conditions_list(
                objective_conditions,
                f"Bloc #{block_id}: ObjectiveConditions",
            )

        if is_objective:
            if bloc.get("Canal"):
                raise ValueError(
                    f"Bloc objectif #{block_id}: ne doit pas avoir de Canal"
                )

            if bloc.get("Action"):
                raise ValueError(
                    f"Bloc objectif #{block_id}: ne doit pas avoir d'Action"
                )

            # Un objectif non-racine doit préciser comment on y entre.
            if parent_ids:
                has_entry_conditions = bool(
                    isinstance(conditions, list)
                    and conditions
                ) or bool(
                    isinstance(conditions_by_parent, dict)
                    and conditions_by_parent
                )

                if not has_entry_conditions:
                    raise ValueError(
                        f"Bloc objectif #{block_id}: conditions d'entrée "
                        "manquantes (Conditions ou ConditionsByParent)"
                    )

            if (
                not isinstance(objective_conditions, list)
                or not objective_conditions
            ):
                raise ValueError(
                    f"Bloc objectif #{block_id}: ObjectiveConditions "
                    "doit être une liste non vide"
                )

        else:
            if not bloc.get("Canal"):
                raise ValueError(
                    f"Bloc normal #{block_id}: Canal obligatoire"
                )

            if not bloc.get("Action"):
                raise ValueError(
                    f"Bloc normal #{block_id}: Action obligatoire"
                )

            if _norm_id(bloc.get("Action")).lower() == "closed":
                raise ValueError(
                    f"Bloc normal #{block_id}: Action='Closed' est obsolète. "
                    "Utiliser un bloc Objectif ; la conversion est portée par conversion=1."
                )

            if objective_conditions is not None:
                raise ValueError(
                    f"Bloc normal #{block_id}: ne doit pas contenir "
                    "ObjectiveConditions"
                )

    id_to_block: Dict[str, Dict[str, Any]] = {
        _norm_id(bloc.get("ID")): bloc
        for bloc in normalized_blocks
    }
    all_ids = set(id_to_block)

    # -----------------------------------------------------
    # 2. Toutes les références Parents doivent exister.
    #    L'auto-parent est explicitement autorisé.
    # -----------------------------------------------------
    for bloc in normalized_blocks:
        block_id = _norm_id(bloc.get("ID"))

        for parent_id in _safe_parent_ids(
            bloc.get("Parents")
        ):
            if parent_id not in all_ids:
                raise ValueError(
                    f"Bloc #{block_id}: parent inexistant '{parent_id}'"
                )

    # -----------------------------------------------------
    # 3. Une seule racine réelle.
    # -----------------------------------------------------
    roots = [
        _norm_id(bloc.get("ID"))
        for bloc in normalized_blocks
        if len(_safe_parent_ids(bloc.get("Parents"))) == 0
    ]

    if len(roots) != 1:
        raise ValueError(
            "Le workflow doit contenir exactement une racine "
            f"(Parents vide). Racines trouvées : {roots}"
        )

    children_map = _build_children_map(
        normalized_blocks
    )

    # -----------------------------------------------------
    # 4. Tout bloc doit appartenir au graphe accessible.
    #    Les cycles restent autorisés.
    # -----------------------------------------------------
    _validate_reachability(
        root_id=roots[0],
        all_ids=all_ids,
        children_map=children_map,
    )

    # -----------------------------------------------------
    # 5. Cohérence des branches objectif.
    # -----------------------------------------------------
    for child in normalized_blocks:
        child_id = _norm_id(child.get("ID"))
        parent_ids = _safe_parent_ids(
            child.get("Parents")
        )

        value = child.get(
            "valide_objectif",
            None,
        )

        if not parent_ids:
            if value is not None and value != "no_goal":
                raise ValueError(
                    f"Bloc racine #{child_id}: valide_objectif doit être "
                    "'no_goal' ou absent"
                )
            continue

        objective_parents = [
            parent_id
            for parent_id in parent_ids
            if bool(
                id_to_block[parent_id].get("objectif")
            )
        ]

        if objective_parents:
            if value not in {"Oui", "Non"}:
                raise ValueError(
                    f"Bloc #{child_id}: enfant d'un ou plusieurs blocs "
                    "objectif, valide_objectif doit être 'Oui' ou 'Non'"
                )
        elif value is not None and value != "no_goal":
            raise ValueError(
                f"Bloc #{child_id}: sans parent objectif, "
                "valide_objectif doit être 'no_goal' ou absent"
            )

    # -----------------------------------------------------
    # 6. Chaque enfant direct d'un objectif doit porter
    #    une branche Oui/Non. Plusieurs fils sont autorisés.
    # -----------------------------------------------------
    for parent_id, parent in id_to_block.items():
        if not bool(parent.get("objectif")):
            continue

        invalid_children = [
            _norm_id(child.get("ID"))
            for child in children_map.get(parent_id, [])
            if child.get("valide_objectif") not in {"Oui", "Non"}
        ]

        if invalid_children:
            raise ValueError(
                f"Bloc objectif #{parent_id}: les fils suivants doivent "
                "avoir valide_objectif='Oui' ou 'Non' : "
                + ", ".join(invalid_children)
            )


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
    ui_positions: Dict[str, Any]  # NEW (stockage positions front)

    # -----------------------------------------------------
    # Constructeur principal
    # -----------------------------------------------------
    @staticmethod
    def new(
        nom_modele: str,
        liste_action: List[Dict[str, Any]],
        graphe_json: Optional[Dict[str, Any]] = None,
        ui_positions: Optional[Dict[str, Any]] = None,  # NEW
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
            ui_positions=ui_positions or {},
        )

    # -----------------------------------------------------
    # JSON serialization
    # -----------------------------------------------------
    def liste_action_json(self) -> str:
        return json.dumps(self.liste_action, ensure_ascii=False)

    def graphe_json_str(self) -> str:
        return json.dumps(self.graphe_json, ensure_ascii=False)
    
    def ui_positions_str(self) -> str:
        return json.dumps(self.ui_positions or {}, ensure_ascii=False)
