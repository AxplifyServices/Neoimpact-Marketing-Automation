# app/domain/workflow_nav.py
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional


def _norm_str(x: Any) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    return "" if s.lower() == "none" else s


def _norm_cmp(x: Any) -> str:
    s = _norm_str(x).lower()
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s).strip()
    return s


def find_bloc_by_id(liste_action: List[Dict[str, Any]], bloc_id: str) -> Optional[Dict[str, Any]]:
    bid = _norm_str(bloc_id)
    for b in liste_action or []:
        if isinstance(b, dict) and _norm_str(b.get("ID")) == bid:
            return b
    return None


def infer_children(liste_action: List[Dict[str, Any]], parent_id: str) -> List[Dict[str, Any]]:
    """Supporte Bloc_mere et Bloc_mère (accent)."""
    pid = _norm_str(parent_id)
    out: List[Dict[str, Any]] = []
    for b in liste_action or []:
        if not isinstance(b, dict):
            continue
        bm = b.get("Bloc_mere") if b.get("Bloc_mere") is not None else b.get("Bloc_mère")
        if _norm_str(bm) == pid:
            out.append(b)
    return out


def _compare(op: str, left: Any, right: Any) -> bool:
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
            if isinstance(right, list):
                return any(_norm_cmp(left) == _norm_cmp(x) for x in right)
            return _norm_cmp(left) in _norm_cmp(right)

    except Exception:
        return False

    return False


def conds_ok(conds: List[Dict[str, Any]], row_cc: Dict[str, Any], resultat_label: str) -> bool:
    """
    Multi-conditions = AND
    Supporte 2 formats :
      - ancien : {Colonne, Operateur, Valeur}
      - nouveau : {field, op, value}

    Mapping UI :
      - "Flag résultats" -> compare à resultat_label (= row_cc["Resultat_last_action"])
      - "NB jours depuis last action" -> row_cc["NB_jour_last_action"]
      - sinon -> row_cc[colonne]
    """
    for c in (conds or []):
        field = _norm_str(c.get("field") or c.get("Colonne"))
        op = _norm_str(c.get("op") or c.get("Operateur")) or "="
        val = c.get("value", c.get("Valeur"))

        if not field:
            continue

        fcmp = _norm_cmp(field)
        if fcmp in (_norm_cmp("Flag résultats"), _norm_cmp("Resultat"), _norm_cmp("Resultat_last_action")):
            left = resultat_label
        elif fcmp in (_norm_cmp("NB jours depuis last action"), _norm_cmp("NB_jour_last_action")):
            left = row_cc.get("NB_jour_last_action")
        else:
            left = row_cc.get(field)

        if not _compare(op, left, val):
            return False

    return True


def pick_next_child(liste_action: List[Dict[str, Any]], current_bloc: Dict[str, Any], row_cc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Choisit le premier fils dont les conditions sont OK.
    - Supporte structure avec "Fils" sinon fallback via Bloc_mere/Bloc_mère
    - Ignore Action='Closed'
    """
    children = current_bloc.get("Fils", None)
    if not isinstance(children, list) or len(children) == 0:
        children = infer_children(liste_action, _norm_str(current_bloc.get("ID")))

    if not isinstance(children, list) or len(children) == 0:
        return None

    resultat_label = _norm_str(row_cc.get("Resultat_last_action"))

    for child in children:
        if not isinstance(child, dict):
            continue
        if _norm_str(child.get("Action")) == "Closed":
            continue

        conds = child.get("Conditions", [])
        if not isinstance(conds, list):
            conds = []

        if conds_ok(conds, row_cc, resultat_label):
            return child

    return None


def objective_reached(statut_actuel: Any, objectif: Any) -> bool:
    """Règle métier: Closed si statut_actuel == objectif (comparaison normalisée)."""
    if not _norm_str(objectif):
        return False
    return _norm_cmp(statut_actuel) == _norm_cmp(objectif)
