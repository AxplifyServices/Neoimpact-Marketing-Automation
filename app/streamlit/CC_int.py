from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from app.domain.canaux import resultats_for_canal
from app.engine.crc_engine import (
    get_next_row_from_queue,
    delete_row_from_queue,
    apply_result_and_update_client_campagnes_from_queue,
)
from app.scripts.batch_manuel import run_batch_manuel

# ✅ façade UI : plus de sqlite3 / DB_PATH dans le front
from app.domain.ui_facades.cc_ui_facade import get_cc_context_from_db


QUEUE_TABLE = "vers_cc"


def _render_header(ctx: Dict[str, Any]) -> None:
    nom_prenom = (" ".join([ctx.get("nom", ""), ctx.get("prenom", "")]).strip()) or "Client"
    st.markdown(f"### {nom_prenom}")

    c1, c2, c3, c4 = st.columns(4, vertical_alignment="center")
    with c1:
        st.caption("Campagne")
        st.write(ctx.get("nom_campagne") or "—")
    with c2:
        st.caption("Variable cible")
        var = ctx.get("variable_cible") or "—"
        val = ctx.get("valeur_cible") or ""
        st.write(f"{var}" + (f" : **{val}**" if val else ""))
    with c3:
        st.caption("Objectif")
        st.write(ctx.get("objectif") or "—")
    with c4:
        st.caption("État actuel")
        st.write(ctx.get("statut_actuel") or "—")

    st.divider()


def main(embedded: bool = False, key_prefix: str = "cc") -> None:
    if not embedded:
        st.title("👤 CC")

    if not embedded:
        if st.button("🔄 Refresh", key=f"{key_prefix}_refresh"):
            run_batch_manuel()
            st.rerun()

    row = get_next_row_from_queue(QUEUE_TABLE)
    if not row:
        st.info("Aucune ligne à traiter dans CC.")
        return

    id_campagne = str(row.get("ID_CAMPAGNE") or "").strip()
    radical = str(row.get("Radical_compte") or "").strip()

    # ✅ contexte DB déplacé hors UI
    ctx = get_cc_context_from_db(id_campagne, radical)
    _render_header(ctx)

    canal = "Conseiller client"
    resultats = resultats_for_canal(canal)

    c1, c2 = st.columns([0.2, 0.8], vertical_alignment="center")

    with c1:
        if st.button("Skip", key=f"{key_prefix}_skip", use_container_width=True):
            delete_row_from_queue(QUEUE_TABLE, id_campagne, radical)
            st.rerun()

    with c2:
        if not resultats:
            st.warning("Aucun résultat défini pour ce canal.")
        else:
            cols = st.columns(len(resultats))
            for col, rlab in zip(cols, resultats):
                with col:
                    if st.button(rlab, key=f"{key_prefix}_res_{rlab}", use_container_width=True):
                        apply_result_and_update_client_campagnes_from_queue(row, rlab, QUEUE_TABLE)
                        st.rerun()
