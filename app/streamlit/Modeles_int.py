from __future__ import annotations

import os
import sys
import json

import streamlit as st
import pandas as pd

# --- Fix imports "app.*" pour Streamlit ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.modeles.modele import Modele, modalites_for
from app.storage.modele_store_sqlite import (
    ensure_modeles_table,
    list_modeles,
    insert_modele,
)
from app.storage.campagnes_store_sqlite import list_campagnes_active


# =========================
# Règles Canal / Action / Résultats
# =========================
CANAL_CHOICES = ["Appel", "Mail", "SMS", "Whatsapp Info", "Whatsapp Questionnaire"]

ACTION_BY_CANAL = {
    "Appel": ["Appeler"],
    "Mail": ["Message"],
    "SMS": ["Message"],
    "Whatsapp Info": ["Message"],
    "Whatsapp Questionnaire": ["Message"],
}

RESULTATS_BY_CANAL = {
    "Appel": ["Joignable avec succès", "Joignable sans succès", "Injoignable"],
    "Mail": ["Transmit", "Non Transmit"],
    "SMS": ["Transmit", "Non Transmit"],
    "Whatsapp Info": ["Délivré", "Non Délivré"],
    "Whatsapp Questionnaire": ["Réponse", "Pas de réponse"],
}

COND_FIELDS = ["Nombre Jour après last action", "Flag résultats", "NB_Appel"]


def _safe_json_load(s: str, default):
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def _blocks_no_closed(blocks: list[dict]) -> list[dict]:
    return [b for b in blocks if b.get("Action") != "Closed"]


def _cond_to_edge_label(cond) -> str:
    if not isinstance(cond, list) or not cond:
        return ""
    parts = []
    for c in cond:
        if not isinstance(c, dict):
            continue
        field = c.get("field", "")
        op = c.get("op", "")
        val = c.get("value", "")
        if field == "Flag résultats":
            parts.append(f"{val}")
        else:
            parts.append(f"{op} {val}".strip())
    return " & ".join([p for p in parts if p])


def build_graph_json(blocks: list[dict]) -> dict:
    nodes = []
    edges = []
    active = _blocks_no_closed(blocks)
    for b in active:
        bid = str(b["ID"])
        nodes.append({"id": bid, "label": b.get("Canal", "")})
    for b in active:
        parent = b.get("Bloc_mere", "")
        if parent and str(parent).isdigit():
            edges.append(
                {"from": str(parent), "to": str(b["ID"]), "label": _cond_to_edge_label(b.get("Condition", []))}
            )
    return {"nodes": nodes, "edges": edges}


def build_dot(blocks: list[dict]) -> str:
    active = _blocks_no_closed(blocks)
    lines = []
    lines.append("digraph G {")
    lines.append("rankdir=LR;")
    lines.append('node [shape=box];')
    for b in active:
        bid = str(b["ID"])
        canal = (b.get("Canal") or "").replace('"', "'")
        lines.append(f'"{bid}" [label="{canal}"];')
    for b in active:
        parent = b.get("Bloc_mere", "")
        if parent and str(parent).isdigit():
            label = _cond_to_edge_label(b.get("Condition", []))
            label = (label or "").replace('"', "'")
            if label:
                lines.append(f'"{parent}" -> "{b["ID"]}" [label="{label}"];')
            else:
                lines.append(f'"{parent}" -> "{b["ID"]}";')
    lines.append("}")
    return "\n".join(lines)


def _ensure_closed_children(blocks: list[dict]) -> list[dict]:
    """
    Ajoute automatiquement un fils Closed à chaque bloc non-Closed si absent.
    ✅ On garantit aussi les clés Objet/Contenu (vides) pour ne rien casser.
    """
    if not blocks:
        return blocks

    existing_ids = {int(b["ID"]) for b in blocks if str(b.get("ID", "")).isdigit()}
    next_id = max(existing_ids) + 1 if existing_ids else 1

    has_closed_child = set()
    for b in blocks:
        bm = b.get("Bloc_mere", "")
        if bm not in ("", None) and str(bm).isdigit() and b.get("Action") == "Closed":
            has_closed_child.add(int(bm))

    parents = [b for b in blocks if b.get("Action") != "Closed"]

    for parent in parents:
        pid = int(parent["ID"])
        if pid in has_closed_child:
            continue
        parent_canal = parent.get("Canal", "Appel")
        blocks.append(
            {
                "ID": next_id,
                "Bloc_mere": str(pid),
                "Condition": [],
                "Canal": parent_canal,
                "Action": "Closed",
                "Resultats_Possibles": RESULTATS_BY_CANAL.get(parent_canal, []),
                "Objet": "",
                "Contenu": "",
            }
        )
        next_id += 1
    return blocks


def _used_flag_results_for_mere(blocks, bloc_mere_id: str):
    used = set()
    for b in blocks:
        if str(b.get("Bloc_mere", "")) != str(bloc_mere_id):
            continue
        cond = b.get("Condition", "")
        if isinstance(cond, list):
            for c in cond:
                if isinstance(c, dict) and c.get("field") == "Flag résultats":
                    used.add(c.get("value"))
    return {u for u in used if u is not None}


def _render_conditions(blocks, block_mere_id: str):
    """
    UI + buffer conditions (ET uniquement)
    ✅ Conditions affichées en tableau
    """
    if "conditions_buffer_modeles" not in st.session_state:
        st.session_state.conditions_buffer_modeles = []
    conds = st.session_state.conditions_buffer_modeles

    if "cond_nonce_modeles" not in st.session_state:
        st.session_state.cond_nonce_modeles = 0

    canal_mere = None
    for b in blocks:
        if str(b.get("ID")) == str(block_mere_id):
            canal_mere = b.get("Canal")
            break

    key_prefix = f"cond_{block_mere_id}_{st.session_state.cond_nonce_modeles}"

    #st.caption("Conditions (ET uniquement) — ajoute une condition puis clique sur « Ajouter la condition »")

    c1, c2, c3 = st.columns([3, 2, 2])

    with c1:
        field = st.selectbox("Champ", COND_FIELDS, key=f"{key_prefix}_field")

    with c2:
        if field == "Flag résultats":
            op = "="
            st.text_input("Opérateur", value="=", disabled=True, key=f"{key_prefix}_op_locked")
        else:
            op = st.selectbox("Opérateur", ["=", ">", "<", ">=", "<="], key=f"{key_prefix}_op")

    with c3:
        if field == "Flag résultats":
            opts = RESULTATS_BY_CANAL.get(canal_mere or "Appel", [])
            used_by_siblings = _used_flag_results_for_mere(blocks, block_mere_id)
            used_in_current = {
                c.get("value")
                for c in conds
                if isinstance(c, dict) and c.get("field") == "Flag résultats"
            }
            forbidden = used_by_siblings.union({u for u in used_in_current if u is not None})
            available = [x for x in opts if x not in forbidden]

            if not available:
                st.warning("Tous les résultats sont déjà utilisés par des fils directs de ce Bloc mère.")
                value = None
                st.selectbox("Valeur", opts, disabled=True, key=f"{key_prefix}_val_flag_disabled")
            else:
                value = st.selectbox("Valeur", available, key=f"{key_prefix}_val_flag")
        else:
            value = st.number_input("Valeur", min_value=0, value=0, step=1, key=f"{key_prefix}_val_num")

    if st.button("➕ Ajouter la condition", key=f"{key_prefix}_add_btn"):
        if field == "Flag résultats" and value is None:
            st.error("Impossible d'ajouter la condition : aucun résultat disponible.")
            st.stop()

        conds.append({"field": field, "join": "ET", "op": op, "value": value})
        st.session_state.conditions_buffer_modeles = conds
        st.session_state.cond_nonce_modeles = st.session_state.get("cond_nonce_modeles", 0) + 1
        st.rerun()

    # ✅ Affichage tableau
    if conds:
        st.markdown("**Conditions ajoutées :**")
        dfc = pd.DataFrame(conds)
        # ordre lisible
        ordered = [c for c in ["field", "join", "op", "value"] if c in dfc.columns]
        dfc = dfc[ordered]
        st.dataframe(dfc, use_container_width=True, height=160)

    return conds


def _render_actions_table(blocks: list[dict]) -> None:
    """Aperçu des actions sous forme de tableau."""
    if not blocks:
        st.caption("Aucune action pour le moment.")
        return

    df = pd.DataFrame(blocks)

    if "Condition" in df.columns:
        df["Condition"] = df["Condition"].apply(
            lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (list, dict)) else x
        )
    if "Resultats_Possibles" in df.columns:
        df["Resultats_Possibles"] = df["Resultats_Possibles"].apply(
            lambda x: ", ".join(x) if isinstance(x, list) else x
        )

    ordered_cols = [
        c for c in ["ID", "Bloc_mere", "Canal", "Action", "Objet", "Contenu", "Resultats_Possibles", "Condition"]
        if c in df.columns
    ]
    df = df[ordered_cols]
    st.dataframe(df, use_container_width=True, height=260)


def main():
    ensure_modeles_table()

    # ✅ INIT GLOBAL
    if "cond_nonce_modeles" not in st.session_state:
        st.session_state.cond_nonce_modeles = 0
    if "conditions_buffer_modeles" not in st.session_state:
        st.session_state.conditions_buffer_modeles = []

    # ✅ modèles verrouillés (campagnes En cours/Planifiée)
    active_camps = list_campagnes_active()
    locked_modele_ids = {str(c.get("id_modele", "")).strip() for c in active_camps if c.get("id_modele")}
    locked_modele_reason = {}
    for c in active_camps:
        mid = str(c.get("id_modele", "")).strip()
        if mid:
            locked_modele_reason[mid] = f"{c.get('id_campagne')} ({c.get('etat_campagne')})"

    # ✅ state propre
    if "show_create_modeles" not in st.session_state:
        st.session_state.show_create_modeles = False

    h1, h2 = st.columns([0.85, 0.15], vertical_alignment="center")
    with h1:
        st.title("Modèles")
    with h2:
        if st.button("➕", key="btn_open_create_modele", help="Créer un modèle"):
            st.session_state.show_create_modeles = True

    # =========================
    # CREATE UI
    # =========================
    if st.session_state.show_create_modeles:
        with st.container(border=True):
            st.subheader("Créer un modèle")

            if "modele_blocks" not in st.session_state:
                st.session_state.modele_blocks = []
            blocks: list[dict] = st.session_state.modele_blocks

            nom_modele = st.text_input("Nom du modèle", value="", key="modele_nom").strip()

            variables = list(modalites_for.__globals__["MODALITES_BY_VARIABLE"].keys())
            variable_cible = st.selectbox("Variable cible", variables, key="modele_variable")

            objectifs = modalites_for(variable_cible)
            objectif = st.selectbox("Objectif", objectifs, key="modele_objectif")

            st.markdown("---")
            st.markdown("### Ajouter une action")

            # ✅ Graphe entre "Ajouter une action" et "Bloc mère"
            st.markdown("#### Graphe")
            if blocks:
                st.graphviz_chart(build_dot(blocks))
            else:
                st.caption("Graphe : (vide pour l’instant)")

            # ✅ Bloc mère: si on a au moins 1 bloc, il ne doit jamais être vide
            if not blocks:
                parents = [""]  # racine autorisée seulement au tout début
                default_index = 0
                st.caption("Premier bloc : le Bloc mère peut être vide (racine).")
            else:
                parents = [str(b["ID"]) for b in blocks if b.get("Action") != "Closed"]
                # default = dernier bloc créé
                default_parent = str(blocks[-1]["ID"])
                default_index = parents.index(default_parent) if default_parent in parents else (len(parents) - 1)

            bloc_mere = st.selectbox("Bloc mère", parents, index=default_index, key="modele_bloc_mere")

            canal = st.selectbox("Canal", CANAL_CHOICES, key="modele_canal")
            action = st.selectbox("Action", ACTION_BY_CANAL.get(canal, ["Message"]), key="modele_action")

            objet = ""
            if canal == "Mail":
                objet = st.text_input("Objet (Mail)", value="", key="modele_objet")

            contenu = st.text_area("Contenu", value="", height=120, key="modele_contenu")

            # ✅ Conditions (obligatoires si blocks non vide, car bloc_mere sera un id)
            st.markdown("### Conditions")
            cond = []
            if bloc_mere != "":
                cond = _render_conditions(blocks, bloc_mere)
            else:
                st.info("La racine (Bloc mère vide) n'a pas de condition.")

            if st.button("➕ Ajouter l'action", key="modele_add_action"):
                next_id = (max([int(b["ID"]) for b in blocks], default=0) + 1)
                new_block = {
                    "ID": next_id,
                    "Bloc_mere": bloc_mere,
                    "Condition": cond if bloc_mere else [],
                    "Canal": canal,
                    "Action": action,
                    "Resultats_Possibles": RESULTATS_BY_CANAL.get(canal, []),
                    "Objet": objet if canal == "Mail" else "",
                    "Contenu": contenu or "",
                }
                blocks.append(new_block)
                st.session_state.modele_blocks = blocks

                # reset buffer conditions après ajout
                st.session_state.conditions_buffer_modeles = []
                st.session_state.cond_nonce_modeles = st.session_state.get("cond_nonce_modeles", 0) + 1
                st.rerun()

            # ✅ Aperçu en tableau
            st.markdown("---")
            st.markdown("### Actions actuelles (aperçu)")
            _render_actions_table(blocks)

            st.markdown("---")
            c_save, c_cancel, c_reset = st.columns([0.25, 0.25, 0.5])

            if c_save.button("✅ Enregistrer le modèle", type="primary", use_container_width=True):
                try:
                    final_blocks = _ensure_closed_children(list(blocks))
                    graphe_json = build_graph_json(final_blocks)

                    m = Modele.new(
                        nom_modele=nom_modele,
                        variable_cible=variable_cible,
                        objectif=objectif,
                        liste_action=final_blocks,
                        graphe_json=graphe_json,
                    )
                    insert_modele(m)

                    st.session_state.modele_blocks = []
                    st.session_state.show_create_modeles = False
                    st.session_state.conditions_buffer_modeles = []
                    st.success("Modèle créé.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

            if c_cancel.button("❌ Annuler", use_container_width=True):
                st.session_state.show_create_modeles = False
                st.session_state.conditions_buffer_modeles = []
                st.rerun()

            if c_reset.button("🧹 Réinitialiser la création", use_container_width=True):
                st.session_state.modele_blocks = []
                st.session_state.conditions_buffer_modeles = []
                st.rerun()

    st.markdown("---")
    st.subheader("Modèles existants")

    rows = list_modeles()
    if not rows:
        st.info("Aucun modèle.")
        return

    for r in rows:
        idm = str(r.get("ID_MODELE", "")).strip()
        nom = r.get("Nom_modele", "")
        vc = r.get("variable_cible", "")
        line = f"{idm} — {nom} — {vc}"

        is_locked = idm in locked_modele_ids

        col_del, col_exp = st.columns([0.06, 0.94], vertical_alignment="center")

        with col_del:
            if st.button(
                "🗑️",
                key=f"del_{idm}",
                help=("Suppression impossible: modèle utilisé par une campagne active." if is_locked else "Supprimer"),
                use_container_width=True,
                disabled=is_locked,
            ):
                try:
                    Modele.delete(idm)
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        with col_exp:
            with st.expander(line, expanded=False):
                if is_locked:
                    st.warning(f"Modèle verrouillé: utilisé par la campagne {locked_modele_reason.get(idm)}")

                st.write(f"**Objectif :** {r.get('Objectif', '')}")
                st.write(f"**Vers CC :** {r.get('vers_cc', '')}")
                st.write(f"**Date :** {r.get('Date_creation', '')}")

                graph_json = _safe_json_load(r.get("graphe_json", ""), {"nodes": [], "edges": []})
                st.markdown("**Graphe JSON (réutilisable Campagnes)**")
                st.json(graph_json)

                actions = _safe_json_load(r.get("liste_action", ""), [])
                if actions:
                    st.markdown("**Aperçu graphe (sans Closed)**")
                    st.graphviz_chart(build_dot(actions))
                else:
                    st.info("Aucune action.")


if __name__ == "__main__":
    main()
