from __future__ import annotations

from typing import Any, Dict, List, Optional
import textwrap


def _s(x: Any) -> str:
    return "" if x is None else str(x).strip()


def _cond_lines(conds: List[Dict[str, Any]]) -> List[str]:
    """
    Transforme les conditions en lignes courtes.
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
                # abréviations
                f = field.replace("NB jours depuis last action", "Jours")
                lines.append(f"{f} {op} {value}")

    # wrap agressif + limite pour éviter explosion
    out: List[str] = []
    for l in lines:
        out.extend(textwrap.wrap(l, width=16) or [l])

    if len(out) > 5:
        out = out[:5] + ["..."]

    return out


def build_dot_from_liste_action(
    blocks: List[Dict[str, Any]],
    variable_cible: str,
    objectif: str,
    selected_id: Optional[int] = None,
    show_closed: bool = False,
) -> str:
    """
    ✅ Anti-chevauchement garanti:
    - on n'écrit PLUS les conditions sur l'arête
    - on insère un mini-noeud "condition" entre parent et enfant
    """
    if not isinstance(blocks, list):
        blocks = []

    visible = blocks if show_closed else [b for b in blocks if _s(b.get("Action")) != "Closed"]
    ids = {b.get("ID") for b in visible}

    dot: List[str] = []
    dot.append("digraph G {")
    dot.append("rankdir=LR;")

    # Layout stable + anti-overlap
    dot.append('graph [overlap=false, splines=true, pack=true, newrank=true, nodesep=0.55, ranksep=0.85, pad=0.10];')

    # Blocs
    dot.append('node [shape=box, style="rounded", margin="0.16,0.10", fontsize=12, fontname="Arial"];')
    dot.append('edge [fontsize=10, fontname="Arial"];')

    # Noeud objectif (compact, pas ellipse géante)
    obj_label = f"{_s(variable_cible)} = {_s(objectif)}".replace('"', "'").strip()
    dot.append(f'"__OBJ__" [shape=box, style="rounded", margin="0.22,0.12", fontsize=12, penwidth=2, label="{obj_label}"];')

    # Noeud style pour conditions (plaintext -> pas de box lourde)
    dot.append('node [shape=plaintext, fontsize=10, fontname="Arial"];')

    # Nodes "action"
    dot.append('node [shape=box, style="rounded", margin="0.16,0.10", fontsize=12, fontname="Arial"];')
    for b in visible:
        bid = b.get("ID")
        if bid is None:
            continue
        canal = _s(b.get("Canal")).replace('"', "'")
        pen = 3 if (selected_id is not None and bid == selected_id) else 1
        dot.append(f'"{bid}" [label="{canal}", penwidth={pen}];')

    # Objectif -> racines
    roots = [b for b in visible if not _s(b.get("Bloc_mère"))]
    for b in roots:
        dot.append(f'"__OBJ__" -> "{b.get("ID")}";')

    # Edges + condition nodes
    cond_node_idx = 0
    for b in visible:
        bid = b.get("ID")
        parent = _s(b.get("Bloc_mère"))

        if parent.isdigit():
            pid = int(parent)
            if pid in ids and bid in ids:
                lines = _cond_lines(b.get("Conditions", []) or [])
                if lines:
                    cond_node_idx += 1
                    cn = f"__C{cond_node_idx}__"
                    label = "\\n".join([x.replace('"', "'") for x in lines])

                    # mini-noeud condition
                    dot.append(f'"{cn}" [shape=plaintext, fontsize=10, label="{label}"];')
                    dot.append(f'"{pid}" -> "{cn}" [arrowhead=none];')
                    dot.append(f'"{cn}" -> "{bid}";')
                else:
                    dot.append(f'"{pid}" -> "{bid}";')

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
