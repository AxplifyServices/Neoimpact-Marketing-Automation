from __future__ import annotations

import os
import sys
from datetime import date

import streamlit as st

# --- Fix imports "app.*" pour Streamlit ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.streamlit._modele_graph import build_dot_from_liste_action, build_dot_from_graphe_json

from app.domain.campagne_service import (
    create_campagne,
    annuler_campagne,
    mettre_en_pause_campagne,
    activer_campagne,
)

# ✅ façade UI (plus de storage/pandas dans le front)
from app.domain.ui_facades.campagne_ui_facade import (
    get_campagnes_affichables_for_ui,
    get_modele_choices_for_ui,
    get_cible_choices_for_ui,
    get_modele_graph_payload_for_ui,
)


# =========================
# Page
# =========================
def main():
    st.set_page_config(page_title="Campagnes", layout="wide")

    h1, h2 = st.columns([0.88, 0.12], vertical_alignment="center")
    h1.title("📣 Campagnes")

    if "show_create" not in st.session_state:
        st.session_state.show_create = False

    if h2.button("➕", help="Créer une campagne", use_container_width=True):
        st.session_state.show_create = not st.session_state.show_create

    # ---- Création
    if st.session_state.show_create:
        st.subheader("Créer une campagne")

        nom = st.text_input("Nom de la campagne", value="").strip()

        # ✅ NEW: description
        description = st.text_area(
            "Description (optionnel)",
            value="",
            height=110,
            placeholder="Décris brièvement l'objectif, le contexte, ou les consignes internes…",
        ).strip()

        c1, c2 = st.columns([1, 1])
        today = date.today()

        # ✅ Dates en session_state + auto-correction (si début > fin => fin = début)
        if "camp_date_debut" not in st.session_state:
            st.session_state["camp_date_debut"] = today
        if "camp_date_fin" not in st.session_state:
            st.session_state["camp_date_fin"] = today

        def _on_change_debut():
            if st.session_state["camp_date_debut"] > st.session_state["camp_date_fin"]:
                st.session_state["camp_date_fin"] = st.session_state["camp_date_debut"]

        def _on_change_fin():
            if st.session_state["camp_date_fin"] < st.session_state["camp_date_debut"]:
                st.session_state["camp_date_fin"] = st.session_state["camp_date_debut"]

        with c1:
            d_debut = st.date_input(
                "Date de début",
                key="camp_date_debut",
                min_value=today,
                on_change=_on_change_debut,
            )

        with c2:
            d_fin = st.date_input(
                "Date de fin",
                key="camp_date_fin",
                min_value=st.session_state["camp_date_debut"],
                on_change=_on_change_fin,
            )

        modele_labels, modele_map = get_modele_choices_for_ui()
        cible_labels, cible_map = get_cible_choices_for_ui()

        if not modele_labels:
            st.warning("Aucun modèle disponible.")
            return
        if not cible_labels:
            st.warning("Aucune cible disponible.")
            return

        mdl_lbl = st.selectbox("Modèle", modele_labels)
        cbl_lbl = st.selectbox("Cible", cible_labels)

        type_campagne = st.selectbox(
            "Type de campagne",
            ["sans_action_terrain", "avec_action_terrain"],
            index=0,
        )

        col_a, col_b = st.columns([0.85, 0.15], vertical_alignment="center")
        with col_b:
            if st.button("✅ Créer", use_container_width=True):
                if not nom:
                    st.error("Nom campagne obligatoire.")
                    st.stop()

                res = create_campagne(
                    nom_campagne=nom,
                    id_modele=modele_map[mdl_lbl],
                    id_cible=cible_map[cbl_lbl],
                    date_debut=d_debut.isoformat(),
                    date_fin=d_fin.isoformat(),
                    description=description,  # ✅ NEW
                    type_campagne=type_campagne,
                )
                st.success(
                    f"Campagne créée ✅ ID={res['id_campagne']} | état={res['etat_campagne']} | "
                    f"cible={res['nb_cible_initial']} | après filtre={res['nb_apres_filtrage']}"
                )
                st.session_state.show_create = False
                st.rerun()

    st.markdown("---")

    # ✅ campagnes affichables via façade (même filtre qu'avant)
    camps = get_campagnes_affichables_for_ui()

    if not camps:
        st.info("Aucune campagne En cours / Planifiée / En pause.")
        return

    # =====================================================
    # Liste (header custom + boutons à droite + contenu toggle)
    # =====================================================
    for c in camps:
        cid = c.get("id_campagne", "")
        nom = c.get("nom_campagne", "")
        etat = c.get("etat_campagne", "") or c.get("etat", "")
        desc = (c.get("description") or "").strip()

        # état open/close par campagne
        toggle_key = f"camp_open_{cid}"
        if toggle_key not in st.session_state:
            st.session_state[toggle_key] = False
        is_open = bool(st.session_state[toggle_key])

        # Header: titre à gauche + boutons à droite (Détails + actions)
        h1c, h2c = st.columns([0.75, 0.25], vertical_alignment="center")

        with h1c:
            st.markdown(
                f"<div style='padding-top:4px;'><b>{cid} — {nom} — {etat}</b></div>",
                unsafe_allow_html=True,
            )

        with h2c:
            # 4 boutons alignés
            b0, b1, b2, b3 = st.columns([1.6, 1, 1, 1])

            # 🔍 Détails (toggle)
            with b0:
                if st.button(
                    "🔍 Détails",
                    key=f"details_{cid}",
                    use_container_width=True,
                ):
                    st.session_state[toggle_key] = not is_open
                    st.rerun()

            # ▶️ Activer
            with b1:
                if st.button(
                    "▶️",
                    key=f"activate_{cid}",
                    help="Activer",
                    disabled=(etat != "En pause"),
                    use_container_width=True,
                ):
                    res = activer_campagne(cid)
                    if res.get("ok"):
                        st.success(f"Campagne réactivée ✅ (nouvel état: {res.get('etat')})")
                    else:
                        st.error(res.get("error", "Erreur activation"))
                    st.rerun()

            # ⏸️ Pause
            with b2:
                if st.button(
                    "⏸️",
                    key=f"pause_{cid}",
                    help="Mettre en pause",
                    disabled=(etat != "En cours"),
                    use_container_width=True,
                ):
                    res = mettre_en_pause_campagne(cid)
                    if res.get("ok"):
                        st.success("Campagne mise en pause ✅")
                    else:
                        st.error(res.get("error", "Erreur mise en pause"))
                    st.rerun()

            # ❌ Annuler
            with b3:
                if st.button("❌", key=f"cancel_{cid}", help="Annuler", use_container_width=True):
                    annuler_campagne(cid)
                    st.rerun()

        # Contenu (affiché/masqué) - inchangé dans le fond
        if is_open:
            with st.container(border=True):
                st.write(f"**Date création :** {c.get('date_creation', '')}")
                st.write(f"**Début :** {c.get('date_debut', '')}")
                st.write(f"**Fin :** {c.get('date_fin', '')}")
                st.write(f"**ID modèle :** {c.get('id_modele', '')}")
                st.write(f"**ID cible :** {c.get('id_cible', '')}")

                # ✅ NEW: description affichée
                st.write(f"**Description :** {desc if desc else '—'}")

                st.markdown("**Graphe du modèle**")

                id_modele = c.get("id_modele", "")
                payload = get_modele_graph_payload_for_ui(id_modele)

                if not payload:
                    st.info("Modèle introuvable pour afficher le graphe.")
                else:
                    liste_action = payload.get("liste_action", []) or []
                    if liste_action:
                        st.graphviz_chart(
                            build_dot_from_liste_action(
                                liste_action,
                                payload.get("variable_cible", "") or "",
                                payload.get("objectif", "") or "",
                                selected_id=None,
                            ),
                            use_container_width=True,
                        )
                    else:
                        graph_json = payload.get("graphe_json", {"nodes": [], "edges": []}) or {"nodes": [], "edges": []}
                        if not graph_json.get("nodes"):
                            st.info("Graphe du modèle vide.")
                        else:
                            st.graphviz_chart(build_dot_from_graphe_json(graph_json), use_container_width=True)

        st.markdown("")  # petite séparation naturelle


if __name__ == "__main__":
    main()
