from __future__ import annotations

import os
import sys
import streamlit as st

# --- Fix imports "app.*" pour Streamlit ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ===== Import des interfaces existantes (doivent exposer main())
from app.streamlit.Campagne_int import main as campagnes_main
from app.streamlit.Historique_int import main as historique_main
from app.streamlit.CRC_int import main as crc_main
from app.streamlit.Dashboard_int import main as dashboard_main
from app.streamlit.Cibles_int import main as cibles_main
from app.streamlit.Modeles_int import main as modeles_main


def creation_view():
    st.title("🧩 Création")
    st.caption("Gérer les Cibles et les Modèles depuis un seul endroit.")

    if "creation_tab" not in st.session_state:
        st.session_state.creation_tab = "Cibles"

    c1, c2, _ = st.columns([0.2, 0.2, 0.6], vertical_alignment="center")
    if c1.button("🎯 Cibles", use_container_width=True):
        st.session_state.creation_tab = "Cibles"
    if c2.button("🧠 Modèles", use_container_width=True):
        st.session_state.creation_tab = "Modèles"

    st.markdown("---")

    if st.session_state.creation_tab == "Cibles":
        cibles_main()
    else:
        modeles_main()


def main():
    st.set_page_config(page_title="Marketing Automation", layout="wide")

    # =========================
    # Sidebar: menu en BLOCKS (pas de radio, pas de checkbox)
    # =========================
    st.markdown(
        """
<style>
/* Sidebar background */
section[data-testid="stSidebar"] > div {
  background: #f2f3f5;              /* gris clair */
  border-right: 1px solid #d9dce1;  /* séparation clean */
}


/* Un peu d'air en haut */
section[data-testid="stSidebar"] .block-container {
  padding-top: 1rem;
}

/* ====== Transforme les boutons Streamlit en "blocks" ======
   Structure typique:
   div[data-testid="stSidebar"] ... div.stButton > button
*/
section[data-testid="stSidebar"] div.stButton > button {
  width: 100% !important;
  text-align: left !important;

  background: #ffffff;            /* bloc clair */
  color: #1f2937;                 /* texte sombre */
  border: 1px solid #d1d5db;
  border-radius: 12px;

  padding: 12px 14px;
  margin: 0;

  cursor: pointer;
  transition: background-color 0.16s ease,
              border-color 0.16s ease,
              transform 0.10s ease;
}

/* Hover */
section[data-testid="stSidebar"] div.stButton > button:hover {
  background: #eef1f6;
  border-color: #c7ccd6;
}

/* Click feedback */
section[data-testid="stSidebar"] div.stButton > button:active {
  transform: scale(0.99);
}


/* Enlève l'outline bleu agressif (reste accessible) */
section[data-testid="stSidebar"] div.stButton > button:focus-visible {
  outline: 2px solid rgba(99, 179, 237, 0.35);
  outline-offset: 2px;
}

/* ====== Style "actif" via une classe appliquée au conteneur ====== */
.nav-active div.stButton > button {
  background: #e6ebf5;
  border-color: #3b82f6;
  color: #111827;
  position: relative;
}

/* Barre gauche */
.nav-active div.stButton > button::before {
  content: "";
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 6px;
  background: #3b82f6;
  border-radius: 8px;
}


/* Espace entre blocks (propre) */
.nav-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>
        """,
        unsafe_allow_html=True,
    )

    PAGES = [
        ("Campagnes", "📣 Campagnes"),
        ("Création", "🧩 Création"),
        ("CRC", "📞 CRC"),
        ("Historique", "🕘 Historique"),
        ("Dashboard", "📊 Dashboard"),    
    ]

    if "active_page" not in st.session_state:
        st.session_state.active_page = "Campagnes"

    with st.sidebar:
        # Pas de titre "Menu" (définitivement)
        st.markdown('<div class="nav-stack">', unsafe_allow_html=True)

        for key, label in PAGES:
            is_active = (st.session_state.active_page == key)

            # Wrapper qui permet de styliser le bouton actif
            if is_active:
                st.markdown('<div class="nav-active">', unsafe_allow_html=True)
            else:
                st.markdown('<div>', unsafe_allow_html=True)

            clicked = st.button(label, key=f"nav_{key}", use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

            if clicked:
                st.session_state.active_page = key
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # =========================
    # Router
    # =========================
    page = st.session_state.active_page

    if page == "Campagnes":
        campagnes_main()

    elif page == "Création":
        creation_view()
    elif page == "CRC":
        crc_main()
    elif page == "Historique":
        historique_main()
    elif page == "Dashboard":
        dashboard_main()

if __name__ == "__main__":
    main()
