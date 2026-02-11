# app/domain/workflow_nav.py
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional

import json


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
      - ✅ "NB jours depuis début de la campagne" -> row_cc["nb_jour_debut_campagne"]
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

        # ✅ NEW : jours depuis début campagne
        elif fcmp in (
            _norm_cmp("NB jours depuis début de la campagne"),
            _norm_cmp("NB jours depuis debut de la campagne"),
            _norm_cmp("NB jours depuis debut campagne"),
            _norm_cmp("NB_jour_debut_campagne"),
            _norm_cmp("nb_jour_debut_campagne"),
            _norm_cmp("Jours depuis début campagne"),
            _norm_cmp("Jours depuis debut campagne"),
        ):
            # colonne en DB: nb_jour_debut_campagne (nouveau)
            # on accepte aussi une éventuelle variante camel/ancienne si jamais
            left = row_cc.get("nb_jour_debut_campagne")
            if left is None:
                left = row_cc.get("NB_jour_debut_campagne")

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
    """
    Compat legacy:
      - objective_reached("Oui", "Oui") -> True

    NEW:
      - objective_reached(row_cc_dict, objectif_json) -> évalue AND/OR sur plusieurs variables
        objectif_json format:
        {"op":"AND|OR","items":[
            {"variable":"Epargne","type":"cat","value":"Oui"},
            {"variable":"NB_appel","type":"num","min":2,"max":5}
        ]}
    """
    obj = _norm_str(objectif).strip()
    if not obj:
        return False

    # =========================
    # ✅ Si on reçoit row_cc (dict)
    # =========================
    if isinstance(statut_actuel, dict):
        row_cc = statut_actuel

        # try parse JSON
        expr = None
        if obj.startswith("{") or obj.startswith("["):
            try:
                expr = json.loads(obj)
            except Exception:
                expr = None

        # multi-objectifs
        if isinstance(expr, dict) and "op" in expr and "items" in expr:
            op = _norm_str(expr.get("op")).upper()
            items = expr.get("items")

            if op not in ("AND", "OR") or not isinstance(items, list) or len(items) == 0:
                return False

            results: List[bool] = []

            for it in items:
                if not isinstance(it, dict):
                    continue

                var = _norm_str(it.get("variable"))
                typ = _norm_str(it.get("type")).lower()

                if not var:
                    continue

                # lecture valeur : d'abord row_cc[var], sinon row_cc["client."+var]
                val = row_cc.get(var)
                if val is None:
                    val = row_cc.get(f"client.{var}")

                # cat
                if typ == "cat":
                    target = _norm_str(it.get("value"))
                    if not target:
                        results.append(False)
                        continue
                    results.append(_norm_cmp(val) == _norm_cmp(target))
                    continue

                # num
                if typ == "num":
                    mn = it.get("min", None)
                    mx = it.get("max", None)

                    try:
                        v = float(str(val).replace(",", "."))
                    except Exception:
                        results.append(False)
                        continue

                    ok = True
                    if mn is not None and str(mn).strip() != "":
                        try:
                            ok = ok and (v >= float(mn))
                        except Exception:
                            ok = False
                    if mx is not None and str(mx).strip() != "":
                        try:
                            ok = ok and (v <= float(mx))
                        except Exception:
                            ok = False

                    results.append(bool(ok))
                    continue

                # type inconnu
                results.append(False)

            if not results:
                return False

            return all(results) if op == "AND" else any(results)

        # fallback legacy sur row_cc["statut_actuel"]
        return _norm_cmp(row_cc.get("statut_actuel")) == _norm_cmp(obj)

    # =========================
    # ✅ Legacy (inchangé)
    # =========================
    return _norm_cmp(statut_actuel) == _norm_cmp(obj)


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
      - sinon, si la différence entre la valeur actuelle et la valeur de condition
        est de 1 ou moins (en valeur absolue) => Oui
    Sinon => "Non".

    Remarques:
    - Les enfants sont déterminés comme dans pick_next_child:
      "Fils" si présent, sinon fallback via infer_children(Bloc_mere/Bloc_mère)
    - Ignore Action == "Closed"
    - Supporte fields: "NB_jour_last_action" et "NB jours depuis last action"
    """

    # 1) Récupère la valeur actuelle NB_jour_last_action depuis la ligne clients_campagnes
    nb = row_cc.get("NB_jour_last_action")
    try:
        nb_val = float(nb)
    except Exception:
        return "Non"  # impossible de comparer proprement

    # 2) Récupère les fils (même logique que pick_next_child)
    children = current_bloc.get("Fils", None)
    if not isinstance(children, list) or len(children) == 0:
        children = infer_children(liste_action, _norm_str(current_bloc.get("ID")))

    if not isinstance(children, list) or len(children) == 0:
        return "Non"

    # 3) Parcours des fils + conditions
    #    On cherche une condition liée à NB_jour_last_action
    for child in children:
        if not isinstance(child, dict):
            continue
        if _norm_str(child.get("Action")) == "Closed":
            continue

        conds = child.get("Conditions", [])
        if not isinstance(conds, list) or len(conds) == 0:
            continue

        for c in conds:
            if not isinstance(c, dict):
                continue

            field = _norm_str(c.get("field") or c.get("Colonne"))
            if not field:
                continue

            fcmp = _norm_cmp(field)
            if fcmp not in (_norm_cmp("NB jours depuis last action"), _norm_cmp("NB_jour_last_action")):
                continue  # pas une condition sur NB_jour_last_action

            op = _norm_str(c.get("op") or c.get("Operateur")) or "="
            val = c.get("value", c.get("Valeur"))

            # valeur cible de la condition
            try:
                target = float(val)
            except Exception:
                # si pas castable, on ne peut pas juger l'échéance
                continue

            # 3.a) Si la condition est déjà satisfaite selon le moteur existant => Oui
            #      (ça couvre =, >=, <=, etc.)
            if _compare(op, nb_val, target):
                return "Oui"

            # 3.b) Sinon, règle "arrive à échéance" : écart <= 1
            if abs(nb_val - target) <= 1.0:
                return "Oui"

    return "Non"
