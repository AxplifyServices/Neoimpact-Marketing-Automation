from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.storage.clients_campagnes_store_sqlite import list_all
from app.storage.campagnes_store_sqlite import list_all_campagnes


def _unique_sorted(vals):
    vals = [v for v in vals if v is not None and str(v).strip() != ""]
    return sorted(list(set(map(lambda x: str(x), vals))))


def main():
    st.set_page_config(page_title="Historique", layout="wide")
    st.title("🕒 Historique")

    data = list_all()
    if not data:
        st.info("Aucune ligne dans clients_campagnes.")
        return

    df = pd.DataFrame(data)

    # ===== Filtres en haut
    st.subheader("Filtres")

    camps = list_all_campagnes()
    camp_ids = ["(Tous)"] + [c["id_campagne"] for c in camps]

    col1, col2, col3, col4, col5 = st.columns(5)

    f_camp = col1.selectbox("Campagne", camp_ids, index=0)

    etats = ["(Tous)"] + _unique_sorted(df.get("Etat_campagne", pd.Series([])).tolist())
    f_etat = col2.selectbox("Etat campagne (client)", etats, index=0)

    rc_search = col3.text_input("Radical_compte contient", value="").strip()

    id_actions = ["(Tous)"] + _unique_sorted(df.get("ID_Action", pd.Series([])).tolist())
    f_id_action = col4.selectbox("ID_Action", id_actions, index=0)

    actions = ["(Tous)"] + _unique_sorted(df.get("Action", pd.Series([])).tolist())
    f_action = col5.selectbox("Action", actions, index=0)

    # ===== Application filtres
    dff = df.copy()

    if f_camp != "(Tous)":
        dff = dff[dff["ID_CAMPAGNE"].astype(str) == str(f_camp)]

    if f_etat != "(Tous)":
        dff = dff[dff["Etat_campagne"].astype(str) == str(f_etat)]

    if rc_search:
        dff = dff[dff["Radical_compte"].astype(str).str.contains(rc_search, case=False, na=False)]

    if f_id_action != "(Tous)":
        dff = dff[dff["ID_Action"].astype(str) == str(f_id_action)]

    if f_action != "(Tous)":
        dff = dff[dff["Action"].astype(str) == str(f_action)]

    st.caption(f"{len(dff)} ligne(s) affichée(s)")

    st.dataframe(dff, use_container_width=True, height=520)


if __name__ == "__main__":
    main()
