from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st
import altair as alt
import plotly.graph_objects as go
import networkx as nx

# --- Fix imports "app.*" pour Streamlit ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.domain.dashboard_kpis import (
    DashboardFilters,
    compute_dashboard_payload,
    get_dynamic_filter_options,
)

# =========================================================
# UI helpers
# =========================================================
def _pct(x: float) -> str:
    try:
        return f"{float(x) * 100:.1f}%"
    except Exception:
        return "0.0%"


def _compact_css():
    st.markdown(
        """
        <style>
          .block-container { padding-top: 0.6rem; padding-bottom: 0.6rem; }
          div[data-testid="stMetric"] { padding: 0.35rem 0.6rem; border: 1px solid rgba(49,51,63,.2); border-radius: 10px; }
          .stMultiSelect div { min-height: 36px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _plot_graph_network(graph_payload: dict, height: int = 290):
    """
    Interactive network graph with Plotly + NetworkX
    - Texte du node: "id + canal"
    - Hover: label complet (avec count)
    """
    nodes = graph_payload.get("nodes", []) or []
    edges = graph_payload.get("edges", []) or []

    if not nodes:
        st.info("Graphe modèle vide pour cette campagne.")
        return

    G = nx.DiGraph()
    for n in nodes:
        nid = str(n.get("id", "")).strip()
        if nid:
            G.add_node(nid, **n)

    for e in edges:
        fr = str(e.get("from", "")).strip()
        to = str(e.get("to", "")).strip()
        if fr and to:
            G.add_edge(fr, to)

    pos = nx.spring_layout(G, seed=7)

    # edges
    edge_x, edge_y = [], []
    for fr, to in G.edges():
        x0, y0 = pos[fr]
        x1, y1 = pos[to]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        mode="lines",
        line=dict(width=1),
        hoverinfo="none",
    )

    # nodes
    node_x, node_y, hovertext, sizes, node_text = [], [], [], [], []
    for nid in G.nodes():
        x, y = pos[nid]
        node_x.append(x)
        node_y.append(y)

        canal = (G.nodes[nid].get("canal") or "").strip()
        cnt = int(G.nodes[nid].get("count") or 0)

        # texte affiché sur le node (compact)
        if canal:
            node_text.append(f"{nid}\n{canal}")
        else:
            node_text.append(f"{nid}")

        # hover détaillé
        label = G.nodes[nid].get("label") or str(nid)
        hovertext.append(label)
        sizes.append(max(12, min(45, 12 + cnt ** 0.5)))

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=node_text,
        textposition="top center",
        hovertext=hovertext,
        hoverinfo="text",
        marker=dict(size=sizes, line=dict(width=1)),
    )

    fig = go.Figure(data=[edge_trace, node_trace])
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=10, b=8),
        showlegend=False,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    st.plotly_chart(fig, use_container_width=True)


# =========================================================
# Main entrypoint for Consolidé router
# =========================================================
def main():
    """
    IMPORTANT:
    - Aucun code Streamlit ne doit s'exécuter au moment de l'import.
    - Consolide_int.py appelle déjà st.set_page_config().
    """
    _compact_css()

    # Session state (namespaced)
    if "dash_selected_etats" not in st.session_state:
        st.session_state["dash_selected_etats"] = ["En cours", "Terminée"]
    if "dash_selected_campaigns" not in st.session_state:
        st.session_state["dash_selected_campaigns"] = []

    # ---------------------------------------------------------
    # Bidirectional dynamic filters
    # ---------------------------------------------------------
    # campaigns depend on selected etats
    opts_for_camps = get_dynamic_filter_options(
        selected_campagne_ids=None,
        selected_etats=st.session_state["dash_selected_etats"],
    )
    allowed_campaign_ids = {o["id"] for o in opts_for_camps["campagnes"]}
    st.session_state["dash_selected_campaigns"] = [
        c for c in st.session_state["dash_selected_campaigns"] if c in allowed_campaign_ids
    ]

    # etats depend on selected campaigns
    opts_for_etats = get_dynamic_filter_options(
        selected_campagne_ids=st.session_state["dash_selected_campaigns"],
        selected_etats=None,
    )
    allowed_etats = {o["value"] for o in opts_for_etats["etats"]}
    st.session_state["dash_selected_etats"] = [
        e for e in st.session_state["dash_selected_etats"] if e in allowed_etats
    ] or list(allowed_etats)

    etat_options = [o["value"] for o in opts_for_etats["etats"]]
    camp_options = opts_for_camps["campagnes"]
    camp_label_by_id = {c["id"]: c["label"] for c in camp_options}

    # ---------------------------------------------------------
    # Filter bar
    # ---------------------------------------------------------
    c1, c2, c3 = st.columns([2.2, 5.0, 1.2], vertical_alignment="bottom")

    with c1:
        st.session_state["dash_selected_etats"] = st.multiselect(
            "État campagne",
            options=etat_options,
            default=st.session_state["dash_selected_etats"],
            key="dash_etats_ui",
        )

    with c2:
        selected_labels = [camp_label_by_id.get(cid, cid) for cid in st.session_state["dash_selected_campaigns"]]
        chosen_labels = st.multiselect(
            "Campagnes",
            options=[c["label"] for c in camp_options],
            default=selected_labels,
            key="dash_camps_ui",
        )
        label_to_id = {c["label"]: c["id"] for c in camp_options}
        st.session_state["dash_selected_campaigns"] = [
            label_to_id[lbl] for lbl in chosen_labels if lbl in label_to_id
        ]

    with c3:
        if st.button("Reset", key="dash_reset"):
            st.session_state["dash_selected_etats"] = ["En cours", "Terminée"]
            st.session_state["dash_selected_campaigns"] = []
            st.rerun()

    # ---------------------------------------------------------
    # Compute payload
    # ---------------------------------------------------------
    filters = DashboardFilters(
        campagne_ids=st.session_state["dash_selected_campaigns"] or None,
        etats_campagne=st.session_state["dash_selected_etats"] or None,
    )
    payload = compute_dashboard_payload(filters)

    kpis = payload.get("kpis", {}) or {}
    by_channel = pd.DataFrame(payload.get("tables", {}).get("by_channel", []) or [])
    region_mix = pd.DataFrame(payload.get("series", {}).get("region_transmit_closed", []) or [])
    funnel = pd.DataFrame(payload.get("series", {}).get("funnel_by_id_action", []) or [])
    daily = pd.DataFrame(payload.get("series", {}).get("daily_treatments_closed", []) or [])

    # ---------------------------------------------------------
    # KPI row
    # ---------------------------------------------------------
    k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
    k1.metric("Clients transmis", int(kpis.get("transmis", 0)))
    k2.metric("Clients contactés", int(kpis.get("contactes_total", 0)))
    k3.metric("Closing", int(kpis.get("closing_total", 0)))
    k4.metric("Total traitements", int(kpis.get("traitements_total", 0)))
    k5.metric("Taux contact", _pct(kpis.get("taux_contact_total", 0.0)))
    k6.metric("Taux closing / affectés", _pct(kpis.get("taux_closing_sur_affectes", 0.0)))
    k7.metric("Arrivés à échéance", int(kpis.get("arriv_eche", 0)))

    # ---------------------------------------------------------
    # Charts row (3)
    # ---------------------------------------------------------
    ch1, ch2, ch3 = st.columns([3, 3, 4], vertical_alignment="top")

    with ch1:
        st.markdown("**Transmis & Closed par région**")
        if region_mix.empty:
            st.info("Aucune donnée.")
        else:
            rm = region_mix.copy()
            melted = rm.melt(
                id_vars=["Region"],
                value_vars=["Transmis", "Closed"],
                var_name="Metric",
                value_name="Value",
            )
            chart = (
                alt.Chart(melted)
                .mark_bar()
                .encode(
                    y=alt.Y("Region:N", sort="-x"),
                    x=alt.X("Value:Q"),
                    color=alt.Color("Metric:N"),
                    tooltip=["Region:N", "Metric:N", "Value:Q"],
                )
                .interactive()
                .properties(height=250)
            )
            st.altair_chart(chart, use_container_width=True)

    with ch2:
        st.markdown("**Funnel d’avancement (ID_Action)**")
        if funnel.empty:
            st.info("Aucune donnée.")
        else:
            chart = (
                alt.Chart(funnel)
                .mark_line(point=True)
                .encode(
                    x=alt.X("ID_Action:N", sort=None),
                    y=alt.Y("Clients:Q"),
                    tooltip=["ID_Action:N", "Clients:Q"],
                )
                .interactive()
                .properties(height=250)
            )
            st.altair_chart(chart, use_container_width=True)

    with ch3:
        st.markdown("**Traitements/jour & Closed/jour**")
        if daily.empty:
            st.info("Aucune donnée.")
        else:
            dd = daily.copy()
            dd["Date"] = pd.to_datetime(dd["Date"])
            melted = dd.melt(
                id_vars=["Date"],
                value_vars=["Traitements", "Closed"],
                var_name="Metric",
                value_name="Value",
            )
            chart = (
                alt.Chart(melted)
                .mark_line(point=True)
                .encode(
                    x=alt.X("Date:T"),
                    y=alt.Y("Value:Q"),
                    color="Metric:N",
                    tooltip=["Date:T", "Metric:N", "Value:Q"],
                )
                .interactive()
                .properties(height=250)
            )
            st.altair_chart(chart, use_container_width=True)

    # ---------------------------------------------------------
    # Bottom row: table + single campaign graph
    # ---------------------------------------------------------
    b1, b2 = st.columns([4, 6], vertical_alignment="top")

    with b1:
        st.markdown("**KPIs par canal**")
        if by_channel.empty:
            st.info("Aucune donnée.")
        else:
            fmt = by_channel.copy()
            for c in ["Taux_closing_sur_traitements", "Taux_contact_sur_transmis"]:
                if c in fmt.columns:
                    fmt[c] = fmt[c].apply(lambda x: _pct(x))
            st.dataframe(fmt, use_container_width=True, height=260)

    with b2:
        if "graph" in payload and payload["graph"].get("nodes"):
            st.markdown("**Graphe campagne (1 campagne sélectionnée)**")
            _plot_graph_network(payload["graph"], height=300)
        else:
            st.markdown("**Graphe campagne**")
            st.info("Sélectionne une seule campagne pour afficher le graphe complet avec les counts dans les nœuds.")


# Standalone run (optional)
if __name__ == "__main__":
    st.set_page_config(page_title="Dashboard", layout="wide")
    main()
