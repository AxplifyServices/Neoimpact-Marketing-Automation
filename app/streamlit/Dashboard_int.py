from __future__ import annotations

import os
import sys
from datetime import date

import pandas as pd
import streamlit as st

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.domain.dashboard_kpis import (
    DashboardFilters,
    compute_backlog_over_time,
    compute_calls_before_success,
    compute_daily_actions,
    compute_overview_kpis,
    compute_success_by_channel,
    load_clients_campagnes_df,
)
from app.storage.campagnes_store_sqlite import list_all_campagnes


# =========================================================
# Helpers
# =========================================================
def _format_pct(x: float) -> str:
    return f"{x * 100:.1f}%" if x else "0.0%"


def _campaign_options() -> tuple[list[str], dict[str, str]]:
    camps = [c for c in list_all_campagnes() if str(c.get("etat_campagne", "")).strip() != "Annulée"]

    labels = []
    mapping = {}
    for c in camps:
        cid = str(c.get("id_campagne", "")).strip()
        nom = str(c.get("nom_campagne", "")).strip()
        etat = str(c.get("etat_campagne", "")).strip()
        label = f"{nom} — {cid} ({etat})" if nom else f"{cid} ({etat})"
        labels.append(label)
        mapping[label] = cid

    return labels, mapping


# =========================================================
# Dashboard
# =========================================================
def main() -> None:
    st.title("📊 Dashboard")
    st.caption("")

    labels, label_to_id = _campaign_options()

    # =========================
    # State
    # =========================
    if "dash_show_filters" not in st.session_state:
        st.session_state.dash_show_filters = False

    if "dash_selected_campaigns" not in st.session_state:
        st.session_state.dash_selected_campaigns = []

    # =========================
    # Campaign filter (SOUS LE TITRE)
    # =========================
    with st.container():
        col_btn, col_info = st.columns([0.25, 0.75], vertical_alignment="center")

        with col_btn:
            if st.button("🎛️ Filtrer par campagnes", use_container_width=True):
                st.session_state.dash_show_filters = not st.session_state.dash_show_filters

        with col_info:
            if st.session_state.dash_selected_campaigns:
                st.info(f"Campagnes sélectionnées : {len(st.session_state.dash_selected_campaigns)} / {len(labels)}")
            else:
                st.info("Toutes les campagnes actives sont incluses")

        if st.session_state.dash_show_filters:
            with st.container(border=True):
                b1, b2 = st.columns(2)
                if b1.button("✅ Tout sélectionner", use_container_width=True):
                    st.session_state.dash_selected_campaigns = labels.copy()

                if b2.button("🧹 Tout désélectionner", use_container_width=True):
                    st.session_state.dash_selected_campaigns = []

                st.session_state.dash_selected_campaigns = st.multiselect(
                    "Campagnes",
                    options=labels,
                    default=st.session_state.dash_selected_campaigns,
                    label_visibility="collapsed",
                )

    selected_ids = (
        [label_to_id[l] for l in st.session_state.dash_selected_campaigns]
        if st.session_state.dash_selected_campaigns
        else None
    )

    st.divider()

    # =========================
    # Load data
    # =========================
    filters = DashboardFilters(campagne_ids=selected_ids)
    df = load_clients_campagnes_df(filters)

    if df.empty:
        st.warning("Aucune donnée disponible avec les filtres actuels.")
        return

    # =========================
    # KPIs
    # =========================
    k = compute_overview_kpis(df)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Clients transmis", f"{k['clients_transmis']:,}".replace(",", " "))
    c2.metric("Clients contactés", f"{k['clients_contactes']:,}".replace(",", " "))
    c3.metric("Objectifs atteints", f"{k['objectifs_atteints']:,}".replace(",", " "))
    c4.metric("Clients en attente", f"{k['clients_en_attente']:,}".replace(",", " "))
    c5.metric("En attente (traitement CC)", f"{k['clients_en_attente_en_traitement']:,}".replace(",", " "))

    c6, c7, c8, c9 = st.columns(4)
    c6.metric("Taux de réussite", _format_pct(k["taux_reussite"]))
    c7.metric("Taux de contact", _format_pct(k["taux_contact"]))
    c8.metric("Nombre d'appels", f"{k['nb_appel']:,}".replace(",", " "))
    c9.metric("Autres interactions", f"{k['nb_mail'] + k['nb_sms'] + k['nb_message']:,}".replace(",", " "))

    st.divider()

    # =========================
    # Mix interactions
    # =========================
    st.subheader("Mix d’interactions")

    vol = pd.DataFrame({
        "Canal": ["Appel", "Mail", "SMS", "Message"],
        "Volume": [k["nb_appel"], k["nb_mail"], k["nb_sms"], k["nb_message"]],
    })

    left, right = st.columns([0.6, 0.4])
    left.bar_chart(vol.set_index("Canal"))

    import altair as alt
    pie = alt.Chart(vol).mark_arc().encode(
        theta="Volume:Q",
        color="Canal:N",
        tooltip=["Canal", "Volume"]
    )
    right.altair_chart(pie, use_container_width=True)

    # =========================
    # Performance par canal
    # =========================
    st.subheader("Performance par canal")
    perf = compute_success_by_channel(df)

    bar = alt.Chart(perf).mark_bar().encode(
        x="Canal:N",
        y=alt.Y("Taux_reussite:Q", axis=alt.Axis(format="%")),
        tooltip=["Canal", "Clients", "Closed"]
    )
    st.altair_chart(bar, use_container_width=True)

    # =========================
    # Time series
    # =========================
    st.subheader("Tendance d’activité")
    daily = compute_daily_actions(df)
    if not daily.empty:
        st.line_chart(daily.set_index("Date")["Actions"])

    st.subheader("Backlog non traité")
    backlog = compute_backlog_over_time(df)
    if not backlog.empty:
        st.line_chart(backlog.set_index("Date")["Backlog_non_traite"])

    # =========================
    # Calls efficiency (sans médiane)
    # =========================
    st.subheader("Efficacité des appels")
    calls = compute_calls_before_success(df)

    e1, e2 = st.columns(2)
    e1.metric("Clients aboutis analysés", int(calls["n_closed"]))
    e2.metric("Moyenne d’appels avant aboutissement", f"{calls['moy_appels_closed']:.2f}")


if __name__ == "__main__":
    main()
