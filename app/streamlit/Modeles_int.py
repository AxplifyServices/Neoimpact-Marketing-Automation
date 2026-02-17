from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

import streamlit as st

# --- Fix imports "app.*" pour Streamlit ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.streamlit._modele_graph import build_dot_from_liste_action
from app.domain.canaux import list_canaux, action_for_canal, resultats_for_canal, compteur_for_canal

from app.domain.ui_facades.modeles_ui_facade import (
    list_modeles_for_ui,
    get_locked_modele_ids_for_ui,
    delete_modele_for_ui,
    get_modele_edit_payload_for_ui,
    save_modele_for_ui,
    get_actions_from_row_for_ui,
    get_client_condition_fields_for_ui,
    get_clients_campagnes_condition_fields_for_ui,
)


# =========================================================
# Helpers UI
# =========================================================
def _pick(d: dict, *keys, default=""):
    for k in keys:
        v = d.get(k, None)
        if v is None:
            continue
        s = str(v).strip()
        if s != "":
            return v
    return default


def _get_block_by_id(blocks_list: List[Dict[str, Any]], bid: int) -> Optional[Dict[str, Any]]:
    for bb in blocks_list:
        if bb.get("Action") == "Closed":
            continue
        if bb.get("ID") == bid:
            return bb
    return None


def _as_int(x: Any) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return None


def _remove_parent_ref(blocks: List[Dict[str, Any]], removed_id: int) -> None:
    rid = str(removed_id)
    for b in blocks:
        p = b.get("Parents")
        if isinstance(p, list):
            b["Parents"] = [str(x) for x in p if str(x) != rid]


def _block_label(b: Dict[str, Any]) -> str:
    bid = b.get("ID")
    if bool(b.get("objectif")):
        return f"#{bid} OBJECTIF"
    canal = str(b.get("Canal", "") or "").strip()
    return f"#{bid} {canal if canal else 'BLOC'}"


# =========================================================
# Conditions builder
# - Catégoriel : modalités + '=' forcé (si modalites dispo)
# - Numérique : Min + Max -> stocké en 2 conditions >= et <= (compat moteur)
# - Champs canal : Flag résultats + compteur dépend du canal parent
# =========================================================
def render_condition_builder(
    bloc_mere: Dict[str, Any],
    key_prefix: str,
    initial_conds: Optional[List[Dict[str, Any]]] = None,
    show_existing: bool = True,
) -> List[Dict[str, Any]]:
    conds_key = f"{key_prefix}_conds"
    init_key = f"{key_prefix}_conds__init"

    if conds_key not in st.session_state:
        st.session_state[conds_key] = []

    # init une seule fois pour éviter reset à chaque rerun
    if initial_conds is not None and not st.session_state.get(init_key, False):
        st.session_state[conds_key] = list(initial_conds or [])
        st.session_state[init_key] = True

    canal_mere = str(bloc_mere.get("Canal", "")).strip()

    if canal_mere in list_canaux():
        compteur = compteur_for_canal(canal_mere)
    else:
        compteur = "NB_message"

    # Champs historiques "système"
    fields = ["Flag résultats", "NB jours depuis last action", compteur]

    # Champs clients.*
    client_meta = get_client_condition_fields_for_ui() or []
    client_labels: List[str] = [f"Client: {d.get('col')}" for d in client_meta if d.get("col")]
    client_label_to_meta = {f"Client: {d.get('col')}": d for d in client_meta if d.get("col")}

    # Champs clients_campagnes : uniquement nb_jour_debut_campagne
    cc_meta = get_clients_campagnes_condition_fields_for_ui() or []
    cc_labels: List[str] = []
    cc_label_to_meta: Dict[str, Dict[str, str]] = {}
    for d in cc_meta:
        col = (d.get("col") or "").strip()
        if col != "nb_jour_debut_campagne":
            continue
        lbl = "NB jours depuis début de la campagne"
        cc_labels.append(lbl)
        cc_label_to_meta[lbl] = d

    def _is_client_label(lbl: str) -> bool:
        return isinstance(lbl, str) and lbl.startswith("Client: ")

    def _is_cc_label(lbl: str) -> bool:
        return lbl in cc_label_to_meta

    def _label_from_stored(field_name: str) -> str:
        f = str(field_name or "")
        if f.startswith("client."):
            return f"Client: {f.split('.', 1)[1]}"
        if f == "nb_jour_debut_campagne":
            return "NB jours depuis début de la campagne"
        return f

    def _stored_from_label(lbl: str) -> str:
        if _is_client_label(lbl):
            return "client." + lbl.split("Client: ", 1)[1].strip()
        if _is_cc_label(lbl):
            return "nb_jour_debut_campagne"
        return lbl

    def _is_numeric_label(lbl: str) -> bool:
        if _is_client_label(lbl):
            return client_label_to_meta.get(lbl, {}).get("is_numeric") == "1"
        if _is_cc_label(lbl):
            return cc_label_to_meta.get(lbl, {}).get("is_numeric") == "1"
        # champs "système"
        if lbl in ["NB jours depuis last action", compteur]:
            return True
        return False

    def _modalites_for_label(lbl: str) -> List[str]:
        # modalites seulement si la façade les expose (sinon fallback)
        if _is_client_label(lbl):
            m = client_label_to_meta.get(lbl, {}) or {}
            mods = m.get("modalites") or m.get("modalites_list") or []
            return list(mods) if isinstance(mods, list) else []
        if _is_cc_label(lbl):
            m = cc_label_to_meta.get(lbl, {}) or {}
            mods = m.get("modalites") or []
            return list(mods) if isinstance(mods, list) else []
        return []

    st.markdown("**Conditions**")

    c1, c2, c3, c4 = st.columns([3, 2, 3, 2])
    all_fields_new = fields + cc_labels + client_labels

    # canal de référence pour "Flag résultats" quand il n'y a pas de canal parent
    default_flag_canal = canal_mere if canal_mere in list_canaux() else (list_canaux()[0] if list_canaux() else "")

    with c1:
        field = st.selectbox("Champ", all_fields_new, key=f"{key_prefix}_field_new")

    # --- Opérateur ---
    with c2:
        mods = _modalites_for_label(field)

        if field == "Flag résultats":
            op = "="
            st.text_input("Opérateur", value="=", disabled=True, key=f"{key_prefix}_op_new_lock_flag")

        elif mods:
            # catégoriel -> '=' forcé
            op = "="
            st.text_input("Opérateur", value="=", disabled=True, key=f"{key_prefix}_op_new_lock_mods")

        elif not _is_numeric_label(field):
            op = st.selectbox("Opérateur", ["=", "!=", "contains", "not contains"], key=f"{key_prefix}_op_new_txt")

        else:
            # numérique -> on stockera min/max en >= et <=
            op = "between"
            st.text_input("Opérateur", value="Min/Max", disabled=True, key=f"{key_prefix}_op_new_lock_between")

    # --- Valeur ---
    with c3:
        mods = _modalites_for_label(field)

        if field == "Flag résultats":
            # valeurs du canal parent, sinon on demande un canal de référence
            flag_canal = st.selectbox(
                "Canal (modalités)",
                list_canaux(),
                index=list_canaux().index(default_flag_canal) if default_flag_canal in list_canaux() else 0,
                key=f"{key_prefix}_flag_canal",
            )
            flag_values = resultats_for_canal(flag_canal) or []
            if flag_values:
                value = st.selectbox("Valeur", flag_values, key=f"{key_prefix}_val_new_flag")
            else:
                value = ""
                st.text_input("Valeur", value="", disabled=True, key=f"{key_prefix}_val_new_flag_empty")

        elif mods:
            value = st.selectbox("Valeur", mods, key=f"{key_prefix}_val_new_mods")

        elif not _is_numeric_label(field):
            value = st.text_input("Valeur", value="", key=f"{key_prefix}_val_new_txt")

        else:
            min_val = st.number_input("Min", min_value=0, step=1, value=0, key=f"{key_prefix}_val_new_num_min")
            max_val = st.number_input("Max", min_value=0, step=1, value=0, key=f"{key_prefix}_val_new_num_max")
            value = {"min": int(min_val), "max": int(max_val)}

    # --- Add ---
    with c4:
        if st.button("➕", key=f"{key_prefix}_add"):
            stored_field = _stored_from_label(field)

            # Numérique min/max -> 2 conditions compatibles moteur
            if isinstance(value, dict) and "min" in value and "max" in value:
                vmin = int(value["min"])
                vmax = int(value["max"])
                st.session_state[conds_key].append({"field": stored_field, "op": ">=", "value": vmin})
                st.session_state[conds_key].append({"field": stored_field, "op": "<=", "value": vmax})
            else:
                st.session_state[conds_key].append({"field": stored_field, "op": "=", "value": value} if field == "Flag résultats" else {"field": stored_field, "op": op if op != "between" else "=", "value": value})

            st.rerun()

    # --- Existing ---
    if show_existing and st.session_state[conds_key]:
        st.markdown("**Conditions existantes**")
        ops_num = ["=", ">", "<", ">=", "<="]
        ops_txt = ["=", "!=", "contains", "not contains"]
        all_fields = fields + cc_labels + client_labels

        for i, c in enumerate(list(st.session_state[conds_key])):
            l, m, r = st.columns([4, 4, 1])

            with l:
                cur_field_label = _label_from_stored(c.get("field"))
                new_field = st.selectbox(
                    "Champ",
                    all_fields,
                    index=all_fields.index(cur_field_label) if cur_field_label in all_fields else 0,
                    key=f"{key_prefix}_field_{i}",
                    label_visibility="collapsed",
                )

            with m:
                mods = _modalites_for_label(new_field)

                # OP
                if new_field == "Flag résultats":
                    new_op = "="
                    st.text_input("Op", value="=", disabled=True, key=f"{key_prefix}_op_{i}_lock_flag", label_visibility="collapsed")

                elif mods:
                    new_op = "="
                    st.text_input("Op", value="=", disabled=True, key=f"{key_prefix}_op_{i}_lock_mods", label_visibility="collapsed")

                elif not _is_numeric_label(new_field):
                    cur_op = c.get("op") if c.get("op") in ops_txt else "="
                    new_op = st.selectbox(
                        "Op",
                        ops_txt,
                        index=ops_txt.index(cur_op),
                        key=f"{key_prefix}_op_{i}_txt",
                        label_visibility="collapsed",
                    )

                else:
                    cur_op = c.get("op") if c.get("op") in ops_num else "="
                    new_op = st.selectbox(
                        "Op",
                        ops_num,
                        index=ops_num.index(cur_op),
                        key=f"{key_prefix}_op_{i}_num",
                        label_visibility="collapsed",
                    )

                # VALUE
                if new_field == "Flag résultats":
                    # canal parent si dispo, sinon canal de ref
                    flag_canal = st.selectbox(
                        "Canal",
                        list_canaux(),
                        index=list_canaux().index(default_flag_canal) if default_flag_canal in list_canaux() else 0,
                        key=f"{key_prefix}_flag_canal_edit_{i}",
                        label_visibility="collapsed",
                    )
                    fv = resultats_for_canal(flag_canal) or []
                    cur_val = str(c.get("value", "") or "")
                    if fv:
                        idx = fv.index(cur_val) if cur_val in fv else 0
                        new_val = st.selectbox("Valeur", fv, index=idx, key=f"{key_prefix}_val_{i}_flag", label_visibility="collapsed")
                    else:
                        new_val = ""
                        st.text_input("Valeur", value="", disabled=True, key=f"{key_prefix}_val_{i}_flag_empty", label_visibility="collapsed")

                elif mods:
                    cur_val = str(c.get("value", "") or "")
                    idx = mods.index(cur_val) if cur_val in mods else 0
                    new_val = st.selectbox("Valeur", mods, index=idx, key=f"{key_prefix}_val_{i}_mods", label_visibility="collapsed")

                elif not _is_numeric_label(new_field):
                    cur_val_txt = str(c.get("value", "") or "")
                    new_val = st.text_input("Valeur", value=cur_val_txt, key=f"{key_prefix}_val_{i}_txt", label_visibility="collapsed")

                else:
                    try:
                        cur_val_num = int(float(c.get("value") or 0))
                    except Exception:
                        cur_val_num = 0
                    new_val = st.number_input(
                        "Valeur",
                        min_value=0,
                        step=1,
                        value=cur_val_num,
                        key=f"{key_prefix}_val_{i}_num",
                        label_visibility="collapsed",
                    )

                st.session_state[conds_key][i] = {"field": _stored_from_label(new_field), "op": new_op, "value": new_val}

            with r:
                if st.button("🗑️", key=f"{key_prefix}_del_{i}"):
                    st.session_state[conds_key].pop(i)
                    st.rerun()

    return list(st.session_state[conds_key])


# =========================================================
# Edit mode
# =========================================================
def _enter_edit_modele(id_modele: str) -> None:
    payload = get_modele_edit_payload_for_ui(id_modele) or {}

    st.session_state["edit_modele_id"] = str(id_modele)
    st.session_state["edit_nom_modele"] = str(payload.get("nom_modele") or "").strip()

    blocks = payload.get("blocks") or []
    if not isinstance(blocks, list):
        blocks = []
    st.session_state["new_blocks"] = blocks

    st.session_state["selected_node"] = None
    st.session_state.pop("cond_builder_conds", None)
    st.session_state.pop("cond_builder_conds__init", None)
    st.session_state["create_mode"] = True


def _exit_edit_modele() -> None:
    st.session_state["edit_modele_id"] = None
    st.session_state["edit_nom_modele"] = ""


# =========================================================
# UI main
# =========================================================
def main():
    st.session_state.setdefault("create_mode", False)
    st.session_state.setdefault("new_blocks", [])
    st.session_state.setdefault("selected_node", None)

    st.session_state.setdefault("edit_modele_id", None)
    st.session_state.setdefault("edit_nom_modele", "")

    # -----------------------------
    # Helpers locaux à main()
    # -----------------------------
    def _is_objective_parent(blocks: List[Dict[str, Any]], pid: str) -> bool:
        try:
            pb = _get_block_by_id(blocks, int(pid))
        except Exception:
            pb = None
        return bool(pb and pb.get("objectif"))

    def _children_of_parent(blocks: List[Dict[str, Any]], parent_id: str) -> List[Dict[str, Any]]:
        out = []
        for b in blocks:
            parents = b.get("Parents") or []
            if not isinstance(parents, list):
                continue
            if parent_id in [str(x) for x in parents]:
                out.append(b)
        return out

    def _allowed_valide_objectif_for_parent(blocks: List[Dict[str, Any]], parent_obj_id: str, current_child_id: Optional[int]) -> List[str]:
        """
        Retourne les options encore disponibles ("Oui"/"Non") pour un parent objectif,
        en tenant compte des enfants existants. Si on édite un enfant déjà branché,
        on libère son choix actuel.
        """
        children = _children_of_parent(blocks, parent_obj_id)

        used = set()
        for c in children:
            if current_child_id is not None and c.get("ID") == current_child_id:
                continue
            used.add(c.get("valide_objectif"))

        opts = []
        if "Oui" not in used:
            opts.append("Oui")
        if "Non" not in used:
            opts.append("Non")
        return opts

    # -----------------------------
    # Header
    # -----------------------------
    top = st.columns([6, 1])
    top[0].title("🧠 Modèles")
    if top[1].button("➕", use_container_width=True):
        _exit_edit_modele()
        st.session_state.create_mode = True
        st.session_state["new_blocks"] = []
        st.session_state["selected_node"] = None
        st.rerun()

    # =====================================================
    # CREATE / EDIT
    # =====================================================
    if st.session_state.create_mode:
        is_editing = bool(st.session_state.get("edit_modele_id"))
        st.subheader("✏️ Modifier un modèle" if is_editing else "Créer un modèle")
        if is_editing:
            st.caption(f"ID modèle : {st.session_state.get('edit_modele_id')}")

        default_nom = st.session_state.get("edit_nom_modele", "") if is_editing else ""
        nom_modele = st.text_input("Nom du modèle", value=default_nom).strip()

        blocks: List[Dict[str, Any]] = st.session_state["new_blocks"]
        visible = [b for b in blocks if b.get("Action") != "Closed"]

        # auto-select
        if len(visible) == 1 and st.session_state["selected_node"] is None:
            st.session_state["selected_node"] = visible[0]["ID"]

        # ===== Graph
        st.markdown("### Aperçu graphe (sans Closed)")
        selected_id = st.session_state["selected_node"]
        if blocks:
            st.graphviz_chart(
                build_dot_from_liste_action(blocks, selected_id=selected_id, show_closed=False),
                use_container_width=True,
            )
        else:
            st.info("Aucun bloc pour le moment.")

        # ===== Select node
        if visible:
            st.markdown("**Sélection d’un bloc**")
            per_row = 4
            for i in range(0, len(visible), per_row):
                row = visible[i : i + per_row]
                cols = st.columns(len(row))
                for col, b in zip(cols, row):
                    bid = b.get("ID")
                    label = _block_label(b)
                    if selected_id is not None and bid == selected_id:
                        label = "✅ " + label
                    with col:
                        if st.button(label, key=f"sel_{bid}"):
                            st.session_state["selected_node"] = int(bid)
                            st.session_state.pop("edit_block_conds", None)
                            st.session_state.pop("edit_block_conds__init", None)
                            st.rerun()

        # ===== Edit selected
        selected_block = _get_block_by_id(blocks, int(selected_id)) if selected_id is not None else None

        if selected_block is not None:
            st.markdown("---")
            st.markdown(f"## Bloc sélectionné : {_block_label(selected_block)}")

            is_obj = bool(selected_block.get("objectif"))
            selected_block_id = int(selected_block.get("ID"))

            # Parents edit
            all_ids = [b.get("ID") for b in visible if b.get("ID") != selected_block.get("ID")]
            all_ids_str = [str(x) for x in all_ids if isinstance(x, int)]

            cur_parents = selected_block.get("Parents")
            if not isinstance(cur_parents, list):
                cur_parents = []
            cur_parents_str = [str(x) for x in cur_parents if str(x).strip()]

            st.markdown("**Parents (multi)**")
            new_parents = st.multiselect(
                "Parents",
                options=all_ids_str,
                default=[p for p in cur_parents_str if p in all_ids_str],
                help="Choisis un ou plusieurs parents. Vide = racine.",
                key="edit_parents_multiselect",
            )

            # -------- NEW: valide_objectif (édition) --------
            objective_parents = [pid for pid in new_parents if _is_objective_parent(blocks, pid)]
            edit_valide_objectif = "no_goal"
            if objective_parents:
                if len(objective_parents) != 1 or len(new_parents) != 1:
                    st.error("Si tu choisis un parent OBJECTIF, le bloc doit avoir exactement 1 seul parent (cet objectif).")
                    st.stop()

                parent_obj_id = objective_parents[0]
                opts = _allowed_valide_objectif_for_parent(blocks, parent_obj_id, current_child_id=selected_block_id)

                # si ce bloc avait déjà Oui/Non, on l’autorise aussi
                cur_vo = selected_block.get("valide_objectif")
                if cur_vo in {"Oui", "Non"} and cur_vo not in opts:
                    opts = [cur_vo] + opts

                if not opts:
                    st.error("Cet objectif a déjà 2 fils (Oui/Non). Impossible de brancher ce bloc dessus.")
                    st.stop()

                cur_vo = selected_block.get("valide_objectif")
                default_idx = opts.index(cur_vo) if cur_vo in opts else 0
                edit_valide_objectif = st.selectbox(
                    "Branchement depuis l'objectif",
                    opts,
                    index=default_idx,
                    key="edit_valide_objectif",
                    help="Oui = objectif validé, Non = objectif non validé",
                )
            else:
                edit_valide_objectif = "no_goal"

            if st.button("✅ Appliquer Parents", use_container_width=True, key="apply_parents"):
                for bb in st.session_state["new_blocks"]:
                    if bb.get("ID") == selected_block.get("ID"):
                        bb["Parents"] = list(new_parents)
                        bb["valide_objectif"] = edit_valide_objectif
                        break
                st.success("Parents mis à jour ✅")
                st.rerun()

            # -------------------------
            # Conditions (objectif)
            # -------------------------
            if is_obj:
                st.markdown("### 🔷 Conditions d'entrée (par parent)")
                cbp = selected_block.get("ConditionsByParent") or {}
                if not isinstance(cbp, dict):
                    cbp = {}

                if new_parents:
                    tmp_cbp: Dict[str, List[Dict[str, Any]]] = {}
                    for pid in new_parents:
                        parent_block = _get_block_by_id(blocks, int(pid)) or {}
                        st.markdown(f"**Depuis le parent #{pid}**")
                        existing = cbp.get(str(pid), [])
                        tmp_cbp[str(pid)] = render_condition_builder(
                            parent_block,
                            key_prefix=f"edit_entry_{pid}",
                            initial_conds=existing if isinstance(existing, list) else [],
                            show_existing=True,
                        )

                    if st.button("✅ Appliquer conditions d'entrée", use_container_width=True, key="apply_entry_conds_obj"):
                        for bb in st.session_state["new_blocks"]:
                            if bb.get("ID") == selected_block.get("ID"):
                                bb["ConditionsByParent"] = tmp_cbp
                                break
                        st.success("Conditions d'entrée mises à jour ✅")
                        st.rerun()
                else:
                    st.info("Bloc racine : pas de conditions d'entrée.")

                # NEW: ObjectiveOperator (uniquement objectifs)
                cur_op = str(selected_block.get("ObjectiveOperator") or "AND").upper()
                obj_operator = st.selectbox(
                    "Combinaison des conditions (AND/OR)",
                    ["AND", "OR"],
                    index=0 if cur_op != "OR" else 1,
                    key="edit_objective_operator",
                )

                st.markdown("### 🎯 Conditions de validation de l'objectif")
                obj_conds = selected_block.get("ObjectiveConditions") or []
                edited_obj_conds = render_condition_builder(
                    {},
                    key_prefix="edit_objective",
                    initial_conds=obj_conds if isinstance(obj_conds, list) else [],
                    show_existing=True,
                )

                if st.button("✅ Appliquer validation objectif", use_container_width=True, key="apply_objective_conds"):
                    for bb in st.session_state["new_blocks"]:
                        if bb.get("ID") == selected_block.get("ID"):
                            bb["ObjectiveConditions"] = edited_obj_conds
                            bb["ObjectiveOperator"] = obj_operator
                            break
                    st.success("Validation objectif mise à jour ✅")
                    st.rerun()

            # -------------------------
            # Conditions (bloc normal)
            # -------------------------
            else:
                st.markdown("### 🔷 Conditions d'entrée (par parent)")
                cbp = selected_block.get("ConditionsByParent") or {}
                if not isinstance(cbp, dict):
                    cbp = {}

                if new_parents:
                    tmp_cbp: Dict[str, List[Dict[str, Any]]] = {}
                    for pid in new_parents:
                        parent_block = _get_block_by_id(blocks, int(pid)) or {}
                        st.markdown(f"**Depuis le parent #{pid}**")
                        existing = cbp.get(str(pid), [])
                        tmp_cbp[str(pid)] = render_condition_builder(
                            parent_block,
                            key_prefix=f"edit_entry_norm_{pid}",
                            initial_conds=existing if isinstance(existing, list) else [],
                            show_existing=True,
                        )

                    if st.button("✅ Appliquer conditions d'entrée", use_container_width=True, key="apply_entry_conds_norm"):
                        for bb in st.session_state["new_blocks"]:
                            if bb.get("ID") == selected_block.get("ID"):
                                bb["ConditionsByParent"] = tmp_cbp
                                break
                        st.success("Conditions d'entrée mises à jour ✅")
                        st.rerun()
                else:
                    st.info("Aucun parent : pas de conditions d'entrée.")

                st.markdown("### Conditions globales (optionnelles)")
                existing_conds = selected_block.get("Conditions") or []
                edited_conds = render_condition_builder(
                    {},
                    key_prefix="edit_block",
                    initial_conds=existing_conds if isinstance(existing_conds, list) else [],
                    show_existing=True,
                )

                if st.button("✅ Appliquer Conditions globales", use_container_width=True, key="apply_global_conds"):
                    for bb in st.session_state["new_blocks"]:
                        if bb.get("ID") == selected_block.get("ID"):
                            bb["Conditions"] = edited_conds
                            break
                    st.success("Conditions globales mises à jour ✅")
                    st.rerun()

            # Delete selected
            if st.button("🗑️ Supprimer ce bloc (sans cascade)", use_container_width=True, key="delete_selected"):
                rid = int(selected_block.get("ID"))
                st.session_state["new_blocks"] = [b for b in blocks if b.get("ID") != rid]
                _remove_parent_ref(st.session_state["new_blocks"], rid)
                st.session_state["selected_node"] = None
                st.rerun()

        st.markdown("---")

        # =====================================================
        # Add new block
        # =====================================================
        st.markdown("## ➕ Ajouter un bloc")

        block_kind = st.radio(
            "Type de bloc",
            ["Bloc normal", "Bloc objectif"],
            horizontal=True,
            help="Bloc objectif = losange + uniquement des conditions (pas de canal/action).",
        )
        is_obj_new = block_kind == "Bloc objectif"

        parent_options = [str(b.get("ID")) for b in visible if isinstance(b.get("ID"), int)]
        default_parents = []
        if st.session_state.get("selected_node") is not None:
            sp = str(st.session_state["selected_node"])
            default_parents = [sp] if sp in parent_options else []

        new_parents = st.multiselect(
            "Parents du nouveau bloc",
            options=parent_options,
            default=default_parents,
            help="Vide = racine.",
            key="new_block_parents",
        )

        # -------- NEW: valide_objectif (création) --------
        objective_parents_new = [pid for pid in new_parents if _is_objective_parent(blocks, pid)]
        valide_objectif_new = "no_goal"

        if objective_parents_new:
            if len(objective_parents_new) != 1 or len(new_parents) != 1:
                st.error("Si tu choisis un parent OBJECTIF, le bloc doit avoir exactement 1 seul parent (cet objectif).")
                st.stop()

            parent_obj_id = objective_parents_new[0]
            opts = _allowed_valide_objectif_for_parent(blocks, parent_obj_id, current_child_id=None)

            if not opts:
                st.error("Cet objectif a déjà 2 fils (Oui/Non). Impossible d'ajouter un 3ème.")
                st.stop()

            valide_objectif_new = st.selectbox(
                "Branchement depuis l'objectif",
                opts,
                key="new_valide_objectif",
                help="Oui = objectif validé, Non = objectif non validé",
            )
        else:
            valide_objectif_new = "no_goal"

        canal = ""
        action = ""
        objet = ""
        contenu = ""

        if not is_obj_new:
            canal = st.selectbox("Canal", list_canaux(), key="new_block_canal")
            action = action_for_canal(canal)

            if canal == "Mail":
                objet = st.text_input("Objet du mail", value="", key="new_block_objet")

            contenu = st.text_area("Contenu", height=120, value="", key="new_block_contenu")

        # Conditions new block
        conditions_by_parent: Dict[str, List[Dict[str, Any]]] = {}
        objective_conditions: List[Dict[str, Any]] = []
        global_conds: List[Dict[str, Any]] = []

        # --- entrée par parent (pour objectif ET normal) ---
        if new_parents:
            st.markdown("### 🔷 Conditions d'entrée (par parent)")
            for pid in new_parents:
                parent_block = _get_block_by_id(blocks, int(pid)) or {}
                st.markdown(f"**Depuis le parent #{pid}**")
                conditions_by_parent[str(pid)] = render_condition_builder(
                    parent_block,
                    key_prefix=f"new_entry_{pid}",
                    initial_conds=[],
                    show_existing=True,
                )
        else:
            st.info("Racine : pas de conditions d'entrée.")

        obj_operator_new = "AND"
        if is_obj_new:
            st.markdown("### 🎯 Conditions de validation de l'objectif")

            # NEW: ObjectiveOperator en création
            obj_operator_new = st.selectbox(
                "Combinaison des conditions (AND/OR)",
                ["AND", "OR"],
                index=0,
                key="new_objective_operator",
            )

            objective_conditions = render_condition_builder(
                {},
                key_prefix="new_objective",
                initial_conds=[],
                show_existing=True,
            )
        else:
            st.markdown("### Conditions globales (optionnelles)")
            global_conds = render_condition_builder(
                {},
                key_prefix="cond_builder",
                initial_conds=[],
                show_existing=True,
            )

        c1, c2, c3 = st.columns([2, 2, 2])

        with c1:
            if st.button("➕ Ajouter", use_container_width=True):
                next_id = 1 if not blocks else (max(int(b.get("ID", 0)) for b in blocks) + 1)

                bloc: Dict[str, Any] = {
                    "ID": next_id,
                    "Parents": list(new_parents),
                    "objectif": bool(is_obj_new),
                    "valide_objectif": valide_objectif_new,
                }

                # Conditions d'entrée pour TOUS (objectif & normal)
                bloc["ConditionsByParent"] = dict(conditions_by_parent)

                if is_obj_new:
                    bloc["ObjectiveConditions"] = list(objective_conditions)
                    bloc["ObjectiveOperator"] = obj_operator_new
                else:
                    bloc["Conditions"] = list(global_conds)
                    bloc.update(
                        {
                            "Canal": canal,
                            "Action": action,
                            "Objet": objet if canal == "Mail" else "",
                            "Contenu": contenu,
                        }
                    )

                st.session_state["new_blocks"].append(bloc)
                st.session_state["selected_node"] = next_id

                # reset builder global
                st.session_state.pop("cond_builder_conds", None)
                st.session_state.pop("cond_builder_conds__init", None)
                st.rerun()

        with c2:
            if st.button("💾 Enregistrer le modèle", type="primary", use_container_width=True):
                if not nom_modele:
                    st.error("Nom du modèle obligatoire.")
                    st.stop()

                try:
                    save_modele_for_ui(
                        is_editing=is_editing,
                        id_modele=str(st.session_state.get("edit_modele_id") or "").strip(),
                        nom_modele=nom_modele,
                        blocks=st.session_state["new_blocks"],
                    )
                    st.success("Modèle mis à jour ✅" if is_editing else "Modèle enregistré ✅")
                except Exception as e:
                    st.error(str(e))
                    st.stop()

                st.session_state["new_blocks"] = []
                st.session_state["selected_node"] = None
                _exit_edit_modele()
                st.session_state.create_mode = False
                st.rerun()

        with c3:
            if st.button("❌ Fermer", use_container_width=True):
                st.session_state["new_blocks"] = []
                st.session_state["selected_node"] = None
                _exit_edit_modele()
                st.session_state.create_mode = False
                st.rerun()

        st.divider()

    # =====================================================
    # LIST
    # =====================================================
    rows = list_modeles_for_ui()
    st.subheader(f"Liste des modèles ({len(rows)})")

    if not rows:
        st.info("Aucun modèle.")
        return

    locked_modele_ids = get_locked_modele_ids_for_ui()

    for idx, r in enumerate(rows):
        mid = str(_pick(r, "ID_MODELE", "id_modele", "Id_modele", default="") or "").strip()
        nom = str(_pick(r, "Nom_modele", "nom_modele", "Nom_Modele", default="") or "").strip()
        is_locked = mid in locked_modele_ids if mid else False

        delete_key = f"del_{mid}" if mid else f"del_idx_{idx}"

        with st.container(border=True):
            a, b, c, d = st.columns([6, 1, 1, 1], vertical_alignment="center")

            a.write(f"**{mid if mid else '(sans id)'}** — {nom if nom else '(sans nom)'}")
            b.write(r.get("date_creation", r.get("Date_creation", "")))

            if c.button("🗑️", key=delete_key, disabled=is_locked or (not mid)):
                delete_modele_for_ui(mid)
                st.rerun()

            if d.button("✏️", key=f"edit_{mid}", disabled=is_locked or (not mid)):
                _enter_edit_modele(mid)
                st.rerun()

            if is_locked:
                st.caption("🔒 Suppression / modification impossible (lié à campagne en cours/planifiée).")

            with st.expander("Détails"):
                actions = get_actions_from_row_for_ui(r)
                if actions:
                    st.markdown("**Aperçu graphe (sans Closed)**")
                    st.graphviz_chart(
                        build_dot_from_liste_action(actions, selected_id=None, show_closed=False),
                        use_container_width=True,
                    )
                    st.code(actions, language="json")
                else:
                    st.info("Aucun bloc.")

if __name__ == "__main__":
    main()
