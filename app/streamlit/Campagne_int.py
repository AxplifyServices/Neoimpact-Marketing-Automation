from __future__ import annotations

import os
import sys
import json
from datetime import date, timedelta

import streamlit as st
import pandas as pd

# --- Fix imports "app.*" pour Streamlit ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.storage.campagnes_store_sqlite import list_campagnes_active, get_campagne
from app.storage.cibles_store_sqlite import list_cibles
from app.storage.modele_store_sqlite import load_db as load_modeles_db
from app.domain.campagne_service import create_campagne, annuler_campagne


# =========================
# Helpers JSON
# =========================
def _safe_json_load(s: str, default):
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


# =========================
# Graphe EXACT du modèle (graphe_json)
# =========================
def build_dot_from_graphe_json(graph_json: dict) -> str:
    """
    graph_json attendu:
    {
      "nodes": [{"id":"1","label":"Appel"}, ...],
      "edges": [{"from":"1","to":"2","label":">= 3"}, ...]
    }
    """
    nodes = graph_json.get("nodes", []) or []
    edges = graph_json.get("edges", []) or []

    lines = []
    lines.append("digraph G {")
    lines.append("rankdir=LR;")  # comme aperçu modèles
    lines.append('node [shape=box];')

    # Nodes
    for n in nodes:
        nid = str(n.get("id", "")).strip()
        lab = str(n.get("label", "")).replace('"', "'")
        if nid:
            lines.append(f'"{nid}" [label="{lab}"];')

    # Edges
    for e in edges:
        a = str(e.get("from", "")).strip()
        b = str(e.get("to", "")).strip()
        lab = str(e.get("label", "") or "").replace('"', "'").strip()
        if a and b:
            if lab:
                lines.append(f'"{a}" -> "{b}" [label="{lab}"];')
            else:
                lines.append(f'"{a}" -> "{b}";')

    lines.append("}")
    return "\n".join(lines)


# =========================
# UI Choices
# =========================
def _modele_choices():
    df = load_modeles_db()
    if df is None or df.empty:
        return [], {}
    labels, mapping = [], {}
    for _, r in df.iterrows():
        lbl = f"{r['ID_MODELE']} — {r['Nom_modele']}"
        labels.append(lbl)
        mapping[lbl] = r["ID_MODELE"]
    return labels, mapping


def _cible_choices():
    cibles = list_cibles()
    labels, mapping = [], {}
    for c in cibles:
        lbl = f"{c['id_cible']} — {c['nom_cible']}"
        labels.append(lbl)
        mapping[lbl] = c["id_cible"]
    return labels, mapping


# =========================
# Page
# =========================
def main():
    st.set_page_config(page_title="Campagnes", layout="wide")

    # Header + bouton plus (haut droite)
    h1, h2 = st.columns([0.88, 0.12], vertical_alignment="center")
    h1.title("📣 Campagnes")

    if "show_create" not in st.session_state:
        st.session_state.show_create = False

    if h2.button("➕", help="Créer une campagne", use_container_width=True):
        st.session_state.show_create = not st.session_state.show_create

    # ---- Création (toggle)
    if st.session_state.show_create:
        st.subheader("Créer une campagne")

        nom = st.text_input("Nom de la campagne", value="").strip()

        c1, c2, c3 = st.columns([1, 1, 1])
        today = date.today()

        # --- init dates en session (une seule fois)
        if "camp_date_debut" not in st.session_state:
            st.session_state["camp_date_debut"] = today
        if "camp_date_fin" not in st.session_state:
            st.session_state["camp_date_fin"] = today + timedelta(days=1)

        # --- callback: si début change -> fin = début + 1 jour (si besoin)
        def _sync_date_fin():
            d0 = st.session_state.get("camp_date_debut")
            d1 = st.session_state.get("camp_date_fin")
            if d0 is None:
                return
            if (d1 is None) or (d1 <= d0):
                st.session_state["camp_date_fin"] = d0 + timedelta(days=1)

        d_debut = c1.date_input(
            "Date de début",
            min_value=today,
            key="camp_date_debut",
            on_change=_sync_date_fin,
        )

        d_fin = c2.date_input(
            "Date de fin",
            min_value=st.session_state["camp_date_debut"],
            key="camp_date_fin",
        )

        # récurrence = Non pour le moment
        c3.radio("Récurrence", ["Non"], index=0, horizontal=True)

        if d_fin < d_debut:
            st.error("Date de fin ne peut pas être avant date de début.")

        modele_labels, modele_map = _modele_choices()
        cible_labels, cible_map = _cible_choices()

        if not modele_labels:
            st.warning("Aucun modèle disponible.")
            return
        if not cible_labels:
            st.warning("Aucune cible disponible.")
            return

        mdl_lbl = st.selectbox("Modèle", modele_labels)
        cbl_lbl = st.selectbox("Cible", cible_labels)

        col_a, col_b = st.columns([0.85, 0.15], vertical_alignment="center")
        with col_a:
            st.caption("")#La campagne sera Planifiée si la date de début est dans le futur, sinon En cours.")
        with col_b:
            if st.button("✅ Créer", use_container_width=True):
                if not nom:
                    st.error("Nom campagne obligatoire.")
                    st.stop()
                if d_fin < d_debut:
                    st.error("Corrige les dates.")
                    st.stop()

                res = create_campagne(
                    nom_campagne=nom,
                    id_modele=modele_map[mdl_lbl],
                    id_cible=cible_map[cbl_lbl],
                    date_debut=d_debut.isoformat(),
                    date_fin=d_fin.isoformat(),
                )
                st.success(
                    f"Campagne créée ✅ ID={res['id_campagne']} | état={res['etat_campagne']} | "
                    f"cible={res['nb_cible_initial']} | après filtre={res['nb_apres_filtrage']}"
                )
                st.session_state.show_create = False
                st.rerun()

    # ---- Liste campagnes (comme Modèles)
    st.markdown("---")
    #st.subheader("Campagnes")

    camps = list_campagnes_active()  # exclut Annulée
    if not camps:
        st.info("Aucune campagne En cours / Planifiée.")
        return

    dfm = load_modeles_db()  # pour récupérer graphe_json
    if dfm is None:
        dfm = pd.DataFrame()

    for c in camps:
        cid = c.get("id_campagne", "")
        nom = c.get("nom_campagne", "")
        etat = c.get("etat_campagne", "")

        line = f"{cid} — {nom} — {etat}"

        # bouton annuler à gauche, expander à droite (même pattern que modèles)
        col_cancel, col_exp = st.columns([0.08, 0.92], vertical_alignment="center")

        with col_cancel:
            if st.button("❌", key=f"cancel_{cid}", help="Annuler", use_container_width=True):
                annuler_campagne(cid)
                st.rerun()

        with col_exp:
            with st.expander(line, expanded=False):
                # détails (uniquement quand on clique)
                st.write(f"**Date création :** {c.get('date_creation', '')}")
                st.write(f"**Début :** {c.get('date_debut', '')}")
                st.write(f"**Fin :** {c.get('date_fin', '')}")
                st.write(f"**ID modèle :** {c.get('id_modele', '')}")
                st.write(f"**ID cible :** {c.get('id_cible', '')}")

                # graphe exact du modèle (graphe_json)
                st.markdown("**Graphe du modèle**")

                id_modele = c.get("id_modele", "")
                row = dfm[dfm["ID_MODELE"] == id_modele] if (not dfm.empty and id_modele) else pd.DataFrame()

                if row.empty:
                    st.info("Modèle introuvable pour afficher le graphe.")
                else:
                    r = row.iloc[0].to_dict()
                    graph_json = _safe_json_load(r.get("graphe_json", ""), {"nodes": [], "edges": []})

                    if not graph_json.get("nodes"):
                        st.info("Graphe du modèle vide.")
                    else:
                        st.graphviz_chart(build_dot_from_graphe_json(graph_json))


if __name__ == "__main__":
    main()
