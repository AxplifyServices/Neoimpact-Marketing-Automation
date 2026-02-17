# app/domain/workflow_nav.py
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional


# =========================================================
# Normalisation
# =========================================================
def _norm_str(x: Any) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    return "" if s.lower() == "none" else s


def _norm_cmp(x: Any) -> str:
    """Lower + strip + remove accents + collapse spaces."""
    s = _norm_str(x).lower()
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s).strip()
    return s


# =========================================================
# Bloc utils
# =========================================================
def find_bloc_by_id(liste_action: List[Dict[str, Any]], bloc_id: str) -> Optional[Dict[str, Any]]:
    bid = _norm_str(bloc_id)
    for b in liste_action or []:
        if isinstance(b, dict) and _norm_str(b.get("ID")) == bid:
            return b
    return None


def is_objective_bloc(bloc: Dict[str, Any]) -> bool:
    return bool(isinstance(bloc, dict) and bloc.get("objectif") is True)


def infer_children(liste_action: List[Dict[str, Any]], parent_id: str) -> List[Dict[str, Any]]:
    """
    Retourne les fils d'un bloc.

    ✅ NEW:
      - utilise Parents: [<parent_id>, ...]
    ✅ Legacy fallback:
      - Bloc_mere / Bloc_mère (accent)
    """
    pid = _norm_str(parent_id)
    out: List[Dict[str, Any]] = []

    # NEW: Parents[]
    for b in liste_action or []:
        if not isinstance(b, dict):
            continue
        parents = b.get("Parents")
        if isinstance(parents, list):
            pset = {_norm_str(x) for x in parents}
            if pid in pset:
                out.append(b)

    if out:
        return out

    # Legacy: Bloc_mere / Bloc_mère
    for b in liste_action or []:
        if not isinstance(b, dict):
            continue
        bm = b.get("Bloc_mere") if b.get("Bloc_mere") is not None else b.get("Bloc_mère")
        if _norm_str(bm) == pid:
            out.append(b)

    return out


# =========================================================
# Comparaisons & Conditions
# =========================================================
def _compare(op: str, left: Any, right: Any) -> bool:
    """
    Compare left <op> right.
    Supporte:
      =, ==, !=, <>, >, <, >=, <=, contains, in
    """
    op = _norm_str(op) or "="
    try:
        if op in ("=", "=="):
            if isinstance(left, str) or isinstance(right, str):
                return _norm_cmp(left) == _norm_cmp(right)
            return left == right

        if op in ("!=", "<>"):
            if isinstance(left, str) or isinstance(right, str):
                return _norm_cmp(left) != _norm_cmp(right)
            return left != right

        if op in (">", "<", ">=", "<="):
            lf = float(left)
            rf = float(right)
            if op == ">":
                return lf > rf
            if op == "<":
                return lf < rf
            if op == ">=":
                return lf >= rf
            if op == "<=":
                return lf <= rf

        if op == "contains":
            return _norm_cmp(right) in _norm_cmp(left)

        if op == "in":
            # right peut être list ou string
            if isinstance(right, list):
                return any(_norm_cmp(left) == _norm_cmp(x) for x in right)
            return _norm_cmp(left) in _norm_cmp(right)

    except Exception:
        return False

    return False


def _resolve_field_value(field_label: str, row_cc: Dict[str, Any], resultat_label: str) -> Any:
    """
    Résout la valeur à comparer pour un label de champ venant de l'UI.

    Mapping conservateur (ne casse pas):
      - "Flag résultats" -> resultat_label (= row_cc["Resultat_last_action"])
      - "NB jours depuis last action" -> row_cc["NB_jour_last_action"]
      - "NB jours depuis début de la campagne" -> row_cc["nb_jour_debut_campagne"] (ou NB_jour_debut_campagne)
      - sinon -> row_cc[field_label] (y compris client.X si enrichi par le batch)
    """
    fcmp = _norm_cmp(field_label)

    if fcmp in (_norm_cmp("Flag résultats"), _norm_cmp("Resultat"), _norm_cmp("Resultat_last_action")):
        return resultat_label

    if fcmp in (_norm_cmp("NB jours depuis last action"), _norm_cmp("NB_jour_last_action")):
        return row_cc.get("NB_jour_last_action")

    if fcmp in (
        _norm_cmp("NB jours depuis début de la campagne"),
        _norm_cmp("NB jours depuis debut de la campagne"),
        _norm_cmp("NB jours depuis debut campagne"),
        _norm_cmp("NB_jour_debut_campagne"),
        _norm_cmp("nb_jour_debut_campagne"),
        _norm_cmp("Jours depuis début campagne"),
        _norm_cmp("Jours depuis debut campagne"),
    ):
        v = row_cc.get("nb_jour_debut_campagne")
        if v is None:
            v = row_cc.get("NB_jour_debut_campagne")
        return v

    # Sinon lecture brute (row_cc est enrichi par le batch: client.X, etc.)
    return row_cc.get(field_label)


def conds_ok(conds: List[Dict[str, Any]], row_cc: Dict[str, Any], resultat_label: str) -> bool:
    """
    Multi-conditions = AND

    Supporte 2 formats:
      - ancien : {Colonne, Operateur, Valeur}
      - nouveau : {field, op, value}
    """
    for c in (conds or []):
        if not isinstance(c, dict):
            continue

        field = _norm_str(c.get("field") or c.get("Colonne"))
        op = _norm_str(c.get("op") or c.get("Operateur")) or "="
        val = c.get("value", c.get("Valeur"))

        if not field:
            continue

        left = _resolve_field_value(field, row_cc, resultat_label)

        if not _compare(op, left, val):
            return False

    return True


def _child_nav_conditions_ok(child: Dict[str, Any], parent_id: str, row_cc: Dict[str, Any]) -> bool:
    """
    Conditions de navigation d'un child en venant de parent_id :
      - child.Conditions (globales)
      + child.ConditionsByParent[parent_id] (spécifiques)
    Le tout en AND.
    """
    if not isinstance(child, dict):
        return False

    pid = _norm_str(parent_id)

    conds_global = child.get("Conditions") or []
    if not isinstance(conds_global, list):
        conds_global = []

    cbp = child.get("ConditionsByParent") or {}
    conds_parent = []
    if isinstance(cbp, dict) and pid:
        # clés stockées parfois en str
        conds_parent = cbp.get(pid) or cbp.get(str(pid)) or []
    if not isinstance(conds_parent, list):
        conds_parent = []

    merged = list(conds_global) + list(conds_parent)

    resultat_label = _norm_str(row_cc.get("Resultat_last_action"))
    return conds_ok(merged, row_cc, resultat_label)


# =========================================================
# Objectif (bloc)
# =========================================================
def _objective_conditions_ok(bloc_objectif: Dict[str, Any], row_cc: Dict[str, Any]) -> bool:
    """
    Évalue ObjectiveConditions d'un bloc objectif.

    - ObjectiveOperator: AND / OR (défaut AND)
    - ObjectiveConditions: liste de conds
    - Chaque cond est évaluée avec le même moteur que la navigation (support client.* etc.)
    """
    if not isinstance(bloc_objectif, dict):
        return False

    conds = bloc_objectif.get("ObjectiveConditions") or []
    if not isinstance(conds, list) or len(conds) == 0:
        return False

    op = _norm_str(bloc_objectif.get("ObjectiveOperator") or "AND").upper()
    if op not in ("AND", "OR"):
        op = "AND"

    resultat_label = _norm_str(row_cc.get("Resultat_last_action"))

    if op == "AND":
        return conds_ok(conds, row_cc, resultat_label)

    # OR: au moins une condition vraie
    for c in conds:
        if conds_ok([c], row_cc, resultat_label):
            return True
    return False


def objective_branch(bloc_objectif: Dict[str, Any], row_cc: Dict[str, Any]) -> str:
    """Retourne 'Oui' si l'objectif est validé, sinon 'Non'."""
    return "Oui" if _objective_conditions_ok(bloc_objectif, row_cc) else "Non"


# =========================================================
# Navigation principale
# =========================================================
def pick_next_child(
    liste_action: List[Dict[str, Any]],
    current_bloc: Dict[str, Any],
    row_cc: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Choisit le prochain bloc (fils) selon ton nouveau format.

    Règles:
      - Si current_bloc est NORMAL:
          - retourne le 1er fils dont les conditions de navigation sont OK
      - Si current_bloc est OBJECTIF:
          - calcule branche Oui/Non via ObjectiveConditions
          - ne considère que les fils avec valide_objectif == 'Oui'/'Non' correspondant
          - puis applique les conditions de navigation (Conditions + ConditionsByParent[current_id])
      - Ignore Action='Closed' (legacy)
    """
    current_id = _norm_str(current_bloc.get("ID"))
    if not current_id:
        return None

    # Fils: nouveau mapping via Parents (sinon fallback legacy)
    children = current_bloc.get("Fils", None)
    if not isinstance(children, list) or len(children) == 0:
        children = infer_children(liste_action, current_id)

    if not isinstance(children, list) or len(children) == 0:
        return None

    is_obj = is_objective_bloc(current_bloc)
    required_valide = None
    if is_obj:
        required_valide = "Oui" if _objective_conditions_ok(current_bloc, row_cc) else "Non"

    for child in children:
        if not isinstance(child, dict):
            continue

        # legacy ignore
        if _norm_str(child.get("Action")) == "Closed":
            continue

        # Filtrage Oui/Non si parent objectif
        if is_obj:
            if _norm_str(child.get("valide_objectif")) != required_valide:
                continue

        # Conditions de navigation
        if _child_nav_conditions_ok(child, current_id, row_cc):
            return child

    return None


# =========================================================
# KPI: Arrive à échéance
# =========================================================
def arrive_echeance(
    liste_action: List[Dict[str, Any]],
    current_bloc: Dict[str, Any],
    row_cc: Dict[str, Any],
) -> str:
    """
    Retourne "Oui" si, parmi les noeuds fils du noeud courant, on trouve
    AU MOINS une condition portant sur NB_jour_last_action (ou son label UI),
    et que l'échéance est "proche" selon la règle :
      - si la condition est déjà satisfaite => Oui
      - sinon, si abs(val_actuelle - val_condition) <= 1 => Oui
    Sinon => "Non".

    ✅ Adapté au nouveau format:
      - les fils viennent de Parents
      - les conditions peuvent être dans Conditions et/ou ConditionsByParent[current_id]
    """
    # valeur actuelle
    nb = row_cc.get("NB_jour_last_action")
    try:
        nb_val = float(nb)
    except Exception:
        return "Non"

    current_id = _norm_str(current_bloc.get("ID"))
    if not current_id:
        return "Non"

    children = current_bloc.get("Fils", None)
    if not isinstance(children, list) or len(children) == 0:
        children = infer_children(liste_action, current_id)

    if not isinstance(children, list) or len(children) == 0:
        return "Non"

    for child in children:
        if not isinstance(child, dict):
            continue
        if _norm_str(child.get("Action")) == "Closed":
            continue

        # on récupère les conditions "effectives" (global + by parent)
        conds_global = child.get("Conditions") or []
        if not isinstance(conds_global, list):
            conds_global = []

        cbp = child.get("ConditionsByParent") or {}
        conds_parent = []
        if isinstance(cbp, dict) and current_id:
            conds_parent = cbp.get(current_id) or cbp.get(str(current_id)) or []
        if not isinstance(conds_parent, list):
            conds_parent = []

        conds = list(conds_global) + list(conds_parent)
        if not conds:
            continue

        for c in conds:
            if not isinstance(c, dict):
                continue
            field = _norm_str(c.get("field") or c.get("Colonne"))
            if not field:
                continue

            fcmp = _norm_cmp(field)
            if fcmp not in (_norm_cmp("NB jours depuis last action"), _norm_cmp("NB_jour_last_action")):
                continue

            op = _norm_str(c.get("op") or c.get("Operateur")) or "="
            val = c.get("value", c.get("Valeur"))

            try:
                target = float(val)
            except Exception:
                continue

            # si la condition est déjà satisfaite
            if _compare(op, nb_val, target):
                return "Oui"

            # sinon proche <= 1
            if abs(nb_val - target) <= 1.0:
                return "Oui"

    return "Non"
