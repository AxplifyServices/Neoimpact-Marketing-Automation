from __future__ import annotations

from typing import Any, Dict, List, Optional
import textwrap


def _s(x: Any) -> str:
    return "" if x is None else str(x).strip()


def _cond_lines(conds: List[Dict[str, Any]]) -> List[str]:
    """
    Transforme les conditions en lignes courtes (pour affichage).
    """
    if not isinstance(conds, list) or not conds:
        return []

    lines: List[str] = []
    for c in conds:
        if not isinstance(c, dict):
            continue

        field = _s(c.get("field"))
        op = _s(c.get("op"))
        value = c.get("value", "")

        if field == "Flag résultats":
            if value not in (None, ""):
                lines.append(_s(value))
        else:
            if field and op and value not in (None, ""):
                f = field.replace("NB jours depuis last action", "Jours")
                lines.append(f"{f} {op} {value}")

    # wrap agressif + limite
    out: List[str] = []
    for l in lines:
        out.extend(textwrap.wrap(l, width=18) or [l])

    if len(out) > 6:
        out = out[:6] + ["..."]

    return out


def _parents_of(b: Dict[str, Any]) -> List[str]:
    """
    Nouveau format: Parents est la seule source.
    - Parents: ["1","2"] ou [1,2]
    - Parents absent => []
    """
    p = b.get("Parents")
    if isinstance(p, list) and p:
        out: List[str] = []
        for x in p:
            s = _s(x)
            if s:
                out.append(s)
        return out
    return []


def _is_objectif_block(b: Dict[str, Any]) -> bool:
    return bool(b.get("objectif"))


def _objective_operator(b: Dict[str, Any]) -> str:
    op = _s(b.get("ObjectiveOperator")).upper()
    return "OR" if op == "OR" else "AND"


def _edge_conds_for_parent(child: Dict[str, Any], parent_id_str: str) -> List[Dict[str, Any]]:
    """
    Retourne les conditions à afficher sur l'arête parent -> child.

    Nouveau modèle :
      - child["ConditionsByParent"][parent_id] = conditions d'entrée depuis CE parent
      - fallback rétrocompat : child["Conditions"] (global)

    Remarque:
      - Pour les blocs objectif: on veut afficher l'entrée (par parent) sur l'arête
        et la validation (ObjectiveConditions) dans le losange.
      - Pour les blocs normaux: même règle, si ConditionsByParent existe on l'utilise,
        sinon on retombe sur Conditions globales.
    """
    cbp = child.get("ConditionsByParent")
    if isinstance(cbp, dict):
        conds = cbp.get(str(parent_id_str))
        if isinstance(conds, list):
            return conds

    conds_global = child.get("Conditions")
    if isinstance(conds_global, list):
        return conds_global

    return []


def build_dot_from_liste_action(
    blocks: List[Dict[str, Any]],
    selected_id: Optional[int] = None,
    show_closed: bool = False,
) -> str:
    """
    Nouveau graph:
    - Multi-parents via Parents[]
    - Bloc objectif (objectif=True) en losange avec les ObjectiveConditions affichées DANS le noeud
      + affichage de ObjectiveOperator (AND/OR)
    - Les conditions de transition restent sur l'arête (mini-noeud condition entre parent et enfant)
      -> on affiche les ConditionsByParent[parent] du BLOC ENFANT (fallback Conditions globales)
    - EXCEPTION: si le parent est un objectif, l'arête affiche seulement Oui/Non (valide_objectif)
    - Plus d'objectif global: on met un noeud __START__ connecté aux racines (Parents vide)
    """
    if not isinstance(blocks, list):
        blocks = []

    # Visible
    visible = blocks if show_closed else [b for b in blocks if _s(b.get("Action")) != "Closed"]
    ids = {b.get("ID") for b in visible}

    dot: List[str] = []
    dot.append("digraph G {")
    dot.append("rankdir=LR;")

    # Layout stable + anti-overlap
    dot.append('graph [overlap=false, splines=true, pack=true, newrank=true, nodesep=0.55, ranksep=0.85, pad=0.10];')

    # Styles
    dot.append('node [shape=box, style="rounded", margin="0.16,0.10", fontsize=12, fontname="Arial"];')
    dot.append('edge [fontsize=10, fontname="Arial"];')

    # START node
    dot.append('"__START__" [shape=box, style="rounded", margin="0.22,0.12", fontsize=12, penwidth=2, label="START"];')

    # Nodes
    for b in visible:
        bid = b.get("ID")
        if bid is None:
            continue

        pen = 3 if (selected_id is not None and bid == selected_id) else 1

        if _is_objectif_block(b):
            op = _objective_operator(b)
            lines = _cond_lines(b.get("ObjectiveConditions", []) or [])
            if lines:
                label = f"OBJECTIF ({op})\\n" + "\\n".join([x.replace('"', "'") for x in lines])
            else:
                label = f"OBJECTIF ({op})"
            dot.append(f'"{bid}" [shape=diamond, style="solid", margin="0.18,0.12", penwidth={pen}, label="{label}"];')
        else:
            canal = _s(b.get("Canal")).replace('"', "'")
            if not canal:
                canal = "BLOC"
            dot.append(f'"{bid}" [shape=box, style="rounded", margin="0.16,0.10", penwidth={pen}, label="{canal}"];')

    # Racines: Parents vide
    roots = [b for b in visible if len(_parents_of(b)) == 0]
    for b in roots:
        dot.append(f'"__START__" -> "{b.get("ID")}";')

    # Condition node style
    dot.append('node [shape=plaintext, fontsize=10, fontname="Arial"];')

    # Edges + mini-noeuds condition
    cond_node_idx = 0

    for child in visible:
        cid = child.get("ID")
        if cid is None:
            continue

        parents = _parents_of(child)
        if not parents:
            continue

        for p in parents:
            if not p.isdigit():
                continue

            pid = int(p)
            if pid not in ids or cid not in ids:
                continue

            # Détecter si le parent est un objectif
            parent_obj = False
            for bb in visible:
                if bb.get("ID") == pid:
                    parent_obj = _is_objectif_block(bb)
                    break

            if parent_obj:
                # Seulement Oui/Non (valide_objectif) sur l'arête
                vo = _s(child.get("valide_objectif"))
                if vo not in {"Oui", "Non"}:
                    vo = ""
                if vo:
                    dot.append(f'"{pid}" -> "{cid}" [label="{vo}"];')
                else:
                    dot.append(f'"{pid}" -> "{cid}";')
                continue

            # Sinon, conditions sur l'arête (ConditionsByParent -> fallback Conditions)
            lines = _cond_lines(_edge_conds_for_parent(child, p) or [])

            if lines:
                cond_node_idx += 1
                cn = f"__C{cond_node_idx}__"
                label = "\\n".join([x.replace('"', "'") for x in lines])

                dot.append(f'"{cn}" [shape=plaintext, fontsize=10, label="{label}"];')
                dot.append(f'"{pid}" -> "{cn}" [arrowhead=none];')
                dot.append(f'"{cn}" -> "{cid}";')
            else:
                dot.append(f'"{pid}" -> "{cid}";')

    dot.append("}")
    return "\n".join(dot)


def build_dot_from_graphe_json(graph_json: Dict[str, Any]) -> str:
    nodes = (graph_json or {}).get("nodes", []) or []
    edges = (graph_json or {}).get("edges", []) or []

    lines: List[str] = []
    lines.append("digraph G {")
    lines.append("rankdir=LR;")
    lines.append('graph [overlap=false, splines=true, pack=true, newrank=true, nodesep=0.55, ranksep=0.85, pad=0.10];')
    lines.append('node [shape=box, style="rounded", margin="0.16,0.10", fontsize=12, fontname="Arial"];')
    lines.append('edge [fontsize=10, fontname="Arial"];')

    for n in nodes:
        nid = _s(n.get("id"))
        lab = _s(n.get("label")).replace('"', "'")
        if nid:
            lines.append(f'"{nid}" [label="{lab}"];')

    for e in edges:
        a = _s(e.get("from"))
        b = _s(e.get("to"))
        if a and b:
            lines.append(f'"{a}" -> "{b}";')

    lines.append("}")
    return "\n".join(lines)
