from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

import streamlit as st

# --- Fix imports "app.*" pour Streamlit ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".", "."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.streamlit._modele_graph import build_dot_from_liste_action

from app.domain.modele import (
    modalites_for,
    normalize_variable_cible,
    objectif_label,
)

from app.domain.canaux import list_canaux, action_for_canal, resultats_for_canal, compteur_for_canal

# ✅ Façade (plus de DB/store direct dans l'UI)
from app.domain.ui_facades.modeles_ui_facade import (
    get_variable_choices_for_ui,
    is_categorical_positive_objectif_for_ui,
    build_numeric_objectif_json_for_ui,
    numeric_objectif_prefill_for_ui,
    list_modeles_for_ui,
    get_locked_modele_ids_for_ui,
    delete_modele_for_ui,
    get_modele_edit_payload_for_ui,
    save_modele_for_ui,
    get_actions_from_row_for_ui,
)


# =========================================================
# Helpers UI (inchangés)
# =========================================================
def _pick(d: dict, *keys, default=""):
    """Récupère la première clé existante et non vide."""
    for k in keys:
        v = d.get(k, None)
        if v is None:
            continue
        s = str(v).strip()
        if s != "":
            return v
    return default


# =========================================================
# Suppression cascade bloc + descendants (inchangé)
# =========================================================
def _descendants_ids(blocks: List[Dict[str, Any]], root_id: int) -> List[int]:
    children_map: Dict[int, List[int]] = {}
    for b in blocks:
        if b.get("Action") == "Closed":
            continue
        bid = b.get("ID")
        parent = str(b.get("Bloc_mère", "")).strip()
        if isinstance(bid, int) and parent.isdigit():
            children_map.setdefault(int(parent), []).append(int(bid))

    to_delete = set()
    stack = [root_id]
    while stack:
        cur = stack.pop()
        if cur in to_delete:
            continue
        to_delete.add(cur)
        for child in children_map.get(cur, []):
            stack.append(child)

    return list(to_delete)


def _parent_id_of(blocks: List[Dict[str, Any]], node_id: int) -> Optional[int]:
    b = next((x for x in blocks if x.get("ID") == node_id), None)
    if not b:
        return None
    parent = str(b.get("Bloc_mère", "")).strip()
    return int(parent) if parent.isdigit() else None


# =========================================================
# Conditions dépendantes du bloc mère (inchangé)
# =========================================================
def render_condition_builder(
    bloc_mere: Dict[str, Any],
    key_prefix: str,
    initial_conds: Optional[List[Dict[str, Any]]] = None,
    show_existing: bool = True,
) -> List[Dict[str, Any]]:
    """
    Builder conditions:
    - Ajout
    - Suppression
    - Modification inline (si show_existing=True)
    - initial_conds sert uniquement à INITIALISER une fois (pas à chaque rerun)
    """
    conds_key = f"{key_prefix}_conds"
    init_key = f"{key_prefix}_conds__init"

    if conds_key not in st.session_state:
        st.session_state[conds_key] = []

    # ✅ IMPORTANT: ne pas réinitialiser à chaque rerun
    if initial_conds is not None and not st.session_state.get(init_key, False):
        st.session_state[conds_key] = list(initial_conds or [])
        st.session_state[init_key] = True

    canal_mere = str(bloc_mere.get("Canal", "")).strip()

    if canal_mere in list_canaux():
        compteur = compteur_for_canal(canal_mere)
        flag_values = resultats_for_canal(canal_mere)
    else:
        compteur = "NB_message"
        flag_values = []

    fields = ["Flag résultats", "NB jours depuis last action", compteur]

    st.markdown("**Conditions (liées au bloc mère sélectionné)**")

    # -------------------------
    # Ajout nouvelle condition
    # -------------------------
    c1, c2, c3, c4 = st.columns([3, 2, 3, 2])

    with c1:
        field = st.selectbox("Champ", fields, key=f"{key_prefix}_field_new")

    with c2:
        if field == "Flag résultats":
            op = "="
            st.text_input("Opérateur", value="=", disabled=True, key=f"{key_prefix}_op_new_lock")
        else:
            op = st.selectbox("Opérateur", ["=", ">", "<", ">=", "<="], key=f"{key_prefix}_op_new")

    with c3:
        if field == "Flag résultats":
            if flag_values:
                value = st.selectbox("Valeur", flag_values, key=f"{key_prefix}_val_new_flag")
            else:
                value = ""
                st.text_input("Valeur", value="", disabled=True, key=f"{key_prefix}_val_new_flag_empty")
        else:
            value = st.number_input("Valeur", min_value=0, step=1, value=0, key=f"{key_prefix}_val_new_num")

    with c4:
        if st.button("➕", key=f"{key_prefix}_add"):
            st.session_state[conds_key].append({"field": field, "op": op, "value": value})
            st.rerun()

    # -------------------------
    # Liste des conditions
    # -------------------------
    if show_existing and st.session_state[conds_key]:
        st.markdown("**Conditions existantes**")
        ops = ["=", ">", "<", ">=", "<="]

        for i, c in enumerate(list(st.session_state[conds_key])):
            l, m, r = st.columns([4, 4, 1])

            with l:
                new_field = st.selectbox(
                    "Champ",
                    fields,
                    index=fields.index(c.get("field")) if c.get("field") in fields else 0,
                    key=f"{key_prefix}_field_{i}",
                    label_visibility="collapsed",
                )

            with m:
                # Op
                if new_field == "Flag résultats":
                    new_op = "="
                    st.text_input(
                        "Op",
                        value="=",
                        disabled=True,
                        key=f"{key_prefix}_op_{i}_lock",
                        label_visibility="collapsed",
                    )
                else:
                    cur_op = c.get("op") if c.get("op") in ops else "="
                    new_op = st.selectbox(
                        "Op",
                        ops,
                        index=ops.index(cur_op),
                        key=f"{key_prefix}_op_{i}",
                        label_visibility="collapsed",
                    )

                # Valeur
                if new_field == "Flag résultats":
                    cur_val = str(c.get("value", "") or "")
                    if flag_values:
                        idx = flag_values.index(cur_val) if cur_val in flag_values else 0
                        new_val = st.selectbox(
                            "Valeur",
                            flag_values,
                            index=idx,
                            key=f"{key_prefix}_val_{i}_flag",
                            label_visibility="collapsed",
                        )
                    else:
                        new_val = ""
                        st.text_input(
                            "Valeur",
                            value="",
                            disabled=True,
                            key=f"{key_prefix}_val_{i}_flag_empty",
                            label_visibility="collapsed",
                        )
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

                # sauvegarde inline dans session
                st.session_state[conds_key][i] = {"field": new_field, "op": new_op, "value": new_val}

            with r:
                if st.button("🗑️", key=f"{key_prefix}_del_{i}"):
                    st.session_state[conds_key].pop(i)
                    st.rerun()

    return list(st.session_state[conds_key])


# =========================================================
# ✅ Mode édition (inchangé côté UX, mais data via façade)
# =========================================================
def _enter_edit_modele(id_modele: str) -> None:
    payload = get_modele_edit_payload_for_ui(id_modele) or {}

    st.session_state["edit_modele_id"] = str(id_modele)
    st.session_state["edit_nom_modele"] = str(payload.get("nom_modele") or "").strip()
    st.session_state["edit_variable_cible"] = str(payload.get("variable_cible") or "").strip()
    st.session_state["edit_objectif"] = payload.get("objectif")

    blocks = payload.get("blocks") or []
    if not isinstance(blocks, list):
        blocks = []
    st.session_state["new_blocks"] = blocks

    st.session_state["selected_bm"] = None
    st.session_state.pop("cond_builder_conds", None)
    st.session_state.pop("cond_builder_conds__init", None)

    st.session_state["create_mode"] = True


def _exit_edit_modele() -> None:
    st.session_state["edit_modele_id"] = None
    st.session_state["edit_nom_modele"] = ""
    st.session_state["edit_variable_cible"] = ""
    st.session_state["edit_objectif"] = None


# =========================================================
# UI
# =========================================================
def main():
    st.session_state.setdefault("create_mode", False)
    st.session_state.setdefault("new_blocks", [])
    st.session_state.setdefault("selected_bm", None)

    # ✅ état édition
    st.session_state.setdefault("edit_modele_id", None)
    st.session_state.setdefault("edit_nom_modele", "")
    st.session_state.setdefault("edit_variable_cible", "")
    st.session_state.setdefault("edit_objectif", None)

    top = st.columns([6, 1])
    top[0].title("🧠 Modèles")
    if top[1].button("➕", use_container_width=True):
        _exit_edit_modele()
        st.session_state.create_mode = True

    # =====================================================
    # CREATE + pré-remplissage si édition (UI identique)
    # =====================================================
    if st.session_state.create_mode:
        st.subheader("Créer un modèle")

        is_editing = bool(st.session_state.get("edit_modele_id"))
        if is_editing:
            st.caption(f"✏️ Modification du modèle : {st.session_state.get('edit_modele_id')}")

        default_nom = st.session_state.get("edit_nom_modele", "") if is_editing else ""
        nom_modele = st.text_input("Nom du modèle", value=default_nom).strip()

        # ✅ choix variables via façade (plus de PRAGMA dans l'UI)
        variable_choices, categorical_cols_allowed, _numeric_cols = get_variable_choices_for_ui()
        if not variable_choices:
            st.error("Aucune colonne cible disponible.")
            st.stop()

        default_var = st.session_state.get("edit_variable_cible", "") if is_editing else ""
        var_index = variable_choices.index(default_var) if (default_var in variable_choices) else 0
        variable_cible = st.selectbox("Colonne cible", variable_choices, index=var_index)

        # ✅ Objectif dépend du type de colonne (même logique)
        is_categorical_positive = is_categorical_positive_objectif_for_ui(variable_cible)

        objectif_value_for_store = ""
        objectif_label_for_ui = ""

        default_obj = st.session_state.get("edit_objectif") if is_editing else None

        if is_categorical_positive:
            objectifs = modalites_for(variable_cible)  # positives only
            if not objectifs:
                st.error(f"Aucune modalité positive définie pour: {variable_cible}")
                st.stop()

            if default_obj in objectifs:
                obj_index = objectifs.index(default_obj)
            else:
                obj_index = 0

            objectif_choice = st.selectbox("Objectif", objectifs, index=obj_index)
            objectif_value_for_store = objectif_choice
            objectif_label_for_ui = objectif_choice
        else:
            st.markdown("**Objectif (numérique)**")

            pre_min, pre_max = numeric_objectif_prefill_for_ui(default_obj) if is_editing else ("", "")

            c1, c2 = st.columns(2)
            with c1:
                mn_txt = st.text_input("Min", value=pre_min, placeholder="(vide = pas de borne)", key="obj_min")
            with c2:
                mx_txt = st.text_input("Max", value=pre_max, placeholder="(vide = pas de borne)", key="obj_max")

            try:
                objectif_value_for_store = build_numeric_objectif_json_for_ui(mn_txt, mx_txt)
                objectif_label_for_ui = objectif_label(variable_cible, objectif_value_for_store)
            except Exception as e:
                st.warning(str(e))
                objectif_value_for_store = ""
                objectif_label_for_ui = ""

        blocks: List[Dict[str, Any]] = st.session_state["new_blocks"]
        visible = [b for b in blocks if b.get("Action") != "Closed"]

        if len(visible) == 1 and st.session_state["selected_bm"] is None:
            st.session_state["selected_bm"] = visible[0]["ID"]

        st.markdown("### Aperçu graphe (sans Closed)")
        selected_id = st.session_state["selected_bm"]
        if blocks:
            st.graphviz_chart(
                build_dot_from_liste_action(
                    blocks,
                    variable_cible,
                    objectif_label_for_ui if objectif_label_for_ui else (objectif_value_for_store or ""),
                    selected_id=selected_id,
                ),
                use_container_width=True,
            )
        else:
            st.info("Aucun bloc pour le moment.")

        # ✅ Choix du bloc mère (inchangé)
        if visible:
            st.markdown("**Sélection du bloc mère**")
            per_row = 6
            for i in range(0, len(visible), per_row):
                row = visible[i : i + per_row]
                cols = st.columns(len(row))
                for col, b in zip(cols, row):
                    bid = b.get("ID")
                    canal_b = b.get("Canal", "")
                    label = f"✅ {canal_b}" if (selected_id is not None and bid == selected_id) else canal_b
                    with col:
                        if st.button(label, key=f"bm_{bid}"):
                            st.session_state["selected_bm"] = int(bid)
                            st.session_state.pop("cond_builder_conds", None)
                            st.session_state.pop("cond_builder_conds__init", None)
                            st.rerun()

        bloc_mere_dict = None
        if selected_id is not None:
            bloc_mere_dict = next((b for b in visible if b.get("ID") == selected_id), None)

        # =====================================================
        # Modifier conditions du bloc sélectionné (inchangé)
        # =====================================================
        def _get_block_by_id(blocks_list: List[Dict[str, Any]], bid: int) -> Optional[Dict[str, Any]]:
            for bb in blocks_list:
                if bb.get("Action") == "Closed":
                    continue
                if bb.get("ID") == bid:
                    return bb
            return None

        def _get_parent_block(blocks_list: List[Dict[str, Any]], child: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            parent = str(child.get("Bloc_mère", "")).strip()
            if not parent.isdigit():
                return None
            return _get_block_by_id(blocks_list, int(parent))

        if selected_id is not None and blocks:
            selected_block = _get_block_by_id(blocks, int(selected_id))
            if selected_block is not None:
                parent_block = _get_parent_block(blocks, selected_block)

                if parent_block is not None:
                    with st.expander("🛠️ Modifier les conditions du bloc sélectionné", expanded=False):
                        existing_conds = selected_block.get("Conditions") or []
                        if not isinstance(existing_conds, list):
                            existing_conds = []

                        edit_prefix = f"edit_block_{int(selected_id)}"

                        edited_conds = render_condition_builder(
                            parent_block,
                            key_prefix=edit_prefix,
                            initial_conds=existing_conds,
                            show_existing=True,
                        )

                        cA, cB = st.columns([2, 2])
                        with cA:
                            if st.button("✅ Appliquer", key=f"{edit_prefix}_apply", use_container_width=True):
                                for bb in st.session_state["new_blocks"]:
                                    if bb.get("ID") == selected_block.get("ID"):
                                        bb["Conditions"] = edited_conds
                                        break
                                st.success("Conditions mises à jour ✅")
                                st.rerun()

                        with cB:
                            if st.button("↩️ Annuler", key=f"{edit_prefix}_cancel", use_container_width=True):
                                st.session_state.pop(f"{edit_prefix}_conds", None)
                                st.session_state.pop(f"{edit_prefix}_conds__init", None)
                                st.rerun()

                    # =====================================================
                    # Modifier contenu + objet (si Mail) (inchangé)
                    # =====================================================
                    with st.expander("✉️ Modifier le contenu du bloc sélectionné", expanded=False):
                        edit_txt_key = f"edit_txt_{int(selected_id)}"
                        edit_obj_key = f"edit_obj_{int(selected_id)}"
                        edit_init_key = f"edit_txt_init_{int(selected_id)}"

                        if not st.session_state.get(edit_init_key, False):
                            st.session_state[edit_txt_key] = str(selected_block.get("Contenu", "") or "")
                            st.session_state[edit_obj_key] = str(selected_block.get("Objet", "") or "")
                            st.session_state[edit_init_key] = True

                        canal_sel = str(selected_block.get("Canal", "") or "").strip()

                        new_obj = st.session_state.get(edit_obj_key, "")
                        if canal_sel == "Mail":
                            new_obj = st.text_input("Objet du mail", key=edit_obj_key)

                        new_txt = st.text_area("Contenu", height=160, key=edit_txt_key)

                        cX, cY = st.columns([2, 2])
                        with cX:
                            if st.button(
                                "✅ Appliquer (contenu/objet)",
                                key=f"apply_txt_{int(selected_id)}",
                                use_container_width=True,
                            ):
                                for bb in st.session_state["new_blocks"]:
                                    if bb.get("Action") == "Closed":
                                        continue
                                    if bb.get("ID") == selected_block.get("ID"):
                                        bb["Contenu"] = new_txt
                                        bb["Objet"] = new_obj if canal_sel == "Mail" else ""
                                        break
                                st.success("Bloc mis à jour ✅")
                                st.rerun()

                        with cY:
                            if st.button(
                                "↩️ Annuler (contenu/objet)",
                                key=f"cancel_txt_{int(selected_id)}",
                                use_container_width=True,
                            ):
                                st.session_state.pop(edit_txt_key, None)
                                st.session_state.pop(edit_obj_key, None)
                                st.session_state.pop(edit_init_key, None)
                                st.rerun()

        # delete bloc + descendants (inchangé)
        if bloc_mere_dict:
            if st.button("🗑️ Supprimer le bloc sélectionné (avec ses fils)"):
                target_id = int(bloc_mere_dict["ID"])
                ids_to_delete = set(_descendants_ids(visible, target_id))
                st.session_state["new_blocks"] = [b for b in blocks if int(b.get("ID")) not in ids_to_delete]

                remaining = [b for b in st.session_state["new_blocks"] if b.get("Action") != "Closed"]
                if not remaining:
                    st.session_state["selected_bm"] = None
                    st.session_state.pop("cond_builder_conds", None)
                    st.session_state.pop("cond_builder_conds__init", None)
                    st.rerun()

                pid = _parent_id_of(visible, target_id)
                st.session_state["selected_bm"] = (
                    pid if (pid is not None and any(b.get("ID") == pid for b in remaining)) else remaining[0]["ID"]
                )
                st.session_state.pop("cond_builder_conds", None)
                st.session_state.pop("cond_builder_conds__init", None)
                st.rerun()

        st.markdown("---")

        canal = st.selectbox("Canal du nouveau bloc", list_canaux())
        action = action_for_canal(canal)

        objet = ""
        if canal == "Mail":
            objet = st.text_input("Objet du mail", value="")

        contenu = st.text_area("Contenu", height=120, value="")

        # ✅ Ajout de conditions uniquement à partir du 2e bloc (inchangé)
        conditions = []
        if blocks and bloc_mere_dict is not None:
            conditions = render_condition_builder(
                bloc_mere_dict,
                key_prefix="cond_builder",
                show_existing=False,
            )

        c1, c2, c3 = st.columns([2, 2, 2])

        with c1:
            if st.button("➕ Ajouter le bloc"):
                parent = "" if not blocks else str(st.session_state["selected_bm"] or "")
                next_id = 1 if not blocks else (max(int(b.get("ID", 0)) for b in blocks) + 1)

                st.session_state["new_blocks"].append(
                    {
                        "ID": next_id,
                        "Bloc_mère": parent,
                        "Canal": canal,
                        "Action": action,
                        "Objet": objet if canal == "Mail" else "",
                        "Contenu": contenu,
                        "Conditions": conditions,
                    }
                )
                st.session_state["selected_bm"] = next_id
                st.session_state.pop("cond_builder_conds", None)
                st.session_state.pop("cond_builder_conds__init", None)
                st.rerun()

        with c2:
            if st.button("💾 Enregistrer le modèle", type="primary"):
                if not nom_modele:
                    st.error("Nom du modèle obligatoire.")
                    st.stop()

                if not objectif_value_for_store:
                    st.error("Objectif invalide / non renseigné.")
                    st.stop()

                try:
                    save_modele_for_ui(
                        is_editing=is_editing,
                        id_modele=str(st.session_state.get("edit_modele_id") or "").strip(),
                        nom_modele=nom_modele,
                        variable_cible=variable_cible,
                        objectif_value_for_store=objectif_value_for_store,
                        blocks=st.session_state["new_blocks"],
                    )
                    st.success("Modèle mis à jour ✅" if is_editing else "Modèle enregistré ✅")
                except Exception as e:
                    st.error(str(e))
                    st.stop()

                st.session_state["new_blocks"] = []
                st.session_state["selected_bm"] = None
                st.session_state.pop("cond_builder_conds", None)
                st.session_state.pop("cond_builder_conds__init", None)
                _exit_edit_modele()
                st.session_state.create_mode = False
                st.rerun()

        with c3:
            if st.button("❌ Fermer"):
                st.session_state["new_blocks"] = []
                st.session_state["selected_bm"] = None
                st.session_state.pop("cond_builder_conds", None)
                st.session_state.pop("cond_builder_conds__init", None)
                _exit_edit_modele()
                st.session_state.create_mode = False
                st.rerun()

        st.divider()

    # =====================================================
    # LIST (bouton ✏️)
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
            b.write(r.get("Date_creation", ""))

            if c.button("🗑️", key=delete_key, disabled=is_locked or (not mid)):
                delete_modele_for_ui(mid)
                st.rerun()

            if d.button("✏️", key=f"edit_{mid}", disabled=is_locked or (not mid)):
                _enter_edit_modele(mid)
                st.rerun()

            if is_locked:
                st.caption("🔒 Suppression / modification impossible (lié à campagne en cours/planifiée).")

            with st.expander("Détails"):
                varc = r.get("variable_cible", "")
                obj = r.get("Objectif", "")

                st.write("Colonne cible :", varc)
                st.write("Objectif :", objectif_label(varc, obj))

                actions = get_actions_from_row_for_ui(r)
                if actions:
                    st.markdown("**Aperçu graphe (sans Closed)**")
                    st.graphviz_chart(
                        build_dot_from_liste_action(
                            actions,
                            varc,
                            objectif_label(varc, obj),
                            selected_id=None,
                        ),
                        use_container_width=True,
                    )
                else:
                    st.info("Aucune action.")


if __name__ == "__main__":
    main()
