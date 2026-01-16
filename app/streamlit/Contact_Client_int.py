from __future__ import annotations

import streamlit as st

from app.scripts.batch_manuel import run_batch_manuel
from app.streamlit.CRC_int import main as crc_main
from app.streamlit.DA_int import main as da_main
from app.streamlit.CC_int import main as cc_main


def main() -> None:
    st.title("☎️ Contact Client")

    # ✅ Refresh obligatoire (meta)
    if st.button("🔄 Refresh", key="contact_refresh"):
        run_batch_manuel()
        st.rerun()

    st.divider()

    if "contact_view" not in st.session_state:
        st.session_state.contact_view = "CRC"

    b1, b2, b3 = st.columns([0.2, 0.2, 0.2], vertical_alignment="center")

    if b1.button("📞 CRC", key="contact_btn_crc", use_container_width=True):
        st.session_state.contact_view = "CRC"
        st.rerun()
    if b2.button("👔 DA", key="contact_btn_da", use_container_width=True):
        st.session_state.contact_view = "DA"
        st.rerun()
    if b3.button("🧑‍💼 CC", key="contact_btn_cc", use_container_width=True):
        st.session_state.contact_view = "CC"
        st.rerun()

    st.markdown("---")

    # ✅ embedded=True => pas de refresh interne, pas de collisions de keys
    if st.session_state.contact_view == "CRC":
        crc_main(embedded=True, key_prefix="embed_crc")
    elif st.session_state.contact_view == "DA":
        da_main(embedded=True, key_prefix="embed_da")
    else:
        cc_main(embedded=True, key_prefix="embed_cc")
