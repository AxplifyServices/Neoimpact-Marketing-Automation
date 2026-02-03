from __future__ import annotations

from typing import Any, Dict, List, Tuple

import streamlit as st

from app.domain.canaux import resultats_for_canal
from app.engine.crc_engine import (
    get_ordered_rows_from_queue,
    move_row_to_end_of_queue,
    get_arrive_eche_flag,
    apply_result_and_update_client_campagnes_from_queue,
    list_campaigns_in_queue,  # ✅ NEW
)
from app.scripts.batch_manuel import run_batch_manuel

# ✅ façade UI : plus de sqlite3 / DB_PATH dans le front
from app.domain.ui_facades.da_ui_facade import get_da_context_from_db


QUEUE_TABLE = "vers_da"


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


def _campaign_filter_ui(queue_table: str, key_prefix: str) -> str | None:
    campaigns: List[Tuple[str, str]] = list_campaigns_in_queue(queue_table)

    options = [("__ALL__", "Toutes les campagnes")]
    options += [(cid, f"{(cname or cid)}  ·  {cid}") for cid, cname in campaigns]

    default_id = st.session_state.get(f"{key_prefix}_camp_filter", "__ALL__")

    default_index = 0
    for i, (cid, _) in enumerate(options):
        if cid == default_id:
            default_index = i
            break

    selected = st.selectbox(
        "Filtrer par campagne",
        options=options,
        index=default_index,
        format_func=lambda x: x[1],
        key=f"{key_prefix}_camp_filter_select",
    )

    selected_id = selected[0]
    st.session_state[f"{key_prefix}_camp_filter"] = selected_id

    return None if selected_id == "__ALL__" else selected_id


def main(embedded: bool = False, key_prefix: str = "da") -> None:
    if not embedded:
        st.title("🏢 DA")

    if not embedded:
        if st.button("🔄 Refresh", key=f"{key_prefix}_refresh"):
            run_batch_manuel()
            st.rerun()

    # ✅ Filtre campagne
    selected_campagne = _campaign_filter_ui(QUEUE_TABLE, key_prefix=key_prefix)

    rows = get_ordered_rows_from_queue(QUEUE_TABLE, id_campagne_filter=selected_campagne)

    # navigation circulaire : on garde la clé courante en session
    state_key = f"{key_prefix}_current_key"
    cur_key = st.session_state.get(state_key)
    if cur_key:
        for i, r in enumerate(rows):
            if str(r.get('ID_CAMPAGNE') or '').strip() == cur_key[0] and str(r.get('Radical_compte') or '').strip() == cur_key[1]:
                current_idx = i
                break
        else:
            current_idx = 0
    else:
        current_idx = 0
    row = rows[current_idx] if rows else None
    if not row:
        if selected_campagne:
            st.info("Aucune ligne DA à traiter pour la campagne sélectionnée.")
        else:
            st.info("Aucune ligne à traiter dans DA.")
        st.session_state.pop(state_key, None)
        return

    id_campagne = str(row.get("ID_CAMPAGNE") or "").strip()
    radical = str(row.get("Radical_compte") or "").strip()

    # mémorise la ligne courante (navigation)
    st.session_state[state_key] = (id_campagne, radical)

    # flag rouge si arrive à échéance
    if get_arrive_eche_flag(id_campagne, radical):
        st.error("⚠️ Client arrivant à échéance")

    # ✅ contexte DB déplacé hors UI
    ctx = get_da_context_from_db(id_campagne, radical)
    _render_header(ctx)

    canal = "Directeur d'agence"
    resultats = resultats_for_canal(canal)

    c1, c2, c3 = st.columns([0.18, 0.18, 0.64], vertical_alignment="center")

    with c1:
        if st.button("⬅️ Reculer", key=f"{key_prefix}_back", use_container_width=True):
            if rows:
                prev_idx = (current_idx - 1) % len(rows)
                prev_row = rows[prev_idx]
                st.session_state[state_key] = (str(prev_row.get('ID_CAMPAGNE') or '').strip(), str(prev_row.get('Radical_compte') or '').strip())
            st.rerun()

    with c2:
        if st.button("Skip", key=f"{key_prefix}_skip", use_container_width=True):
            if rows:
                next_idx = (current_idx + 1) % len(rows)
                next_row = rows[next_idx]
                st.session_state[state_key] = (str(next_row.get('ID_CAMPAGNE') or '').strip(), str(next_row.get('Radical_compte') or '').strip())
            move_row_to_end_of_queue(QUEUE_TABLE, id_campagne, radical)
            st.rerun()

    with c3:
        if not resultats:
            st.warning("Aucun résultat défini pour ce canal.")
        else:
            cols = st.columns(len(resultats))
            for col, rlab in zip(cols, resultats):
                with col:
                    if st.button(rlab, key=f"{key_prefix}_res_{rlab}", use_container_width=True):
                        apply_result_and_update_client_campagnes_from_queue(row, rlab, QUEUE_TABLE)
                        st.rerun()
