from __future__ import annotations

import streamlit as st
from typing import Any, Dict, List, Tuple

from app.storage.db import get_table_columns, insert_client_if_new


CLIENT_TABLE = "clients"


def _is_numeric_sqlite_type(t: str) -> bool:
    tt = (t or "").upper()
    return any(x in tt for x in ["INT", "REAL", "NUM", "DEC", "DOUBLE", "FLOAT"])


def _is_date_like(t: str) -> bool:
    tt = (t or "").upper()
    return any(x in tt for x in ["DATE", "DATETIME", "TIMESTAMP"])


def _normalize_value(v: Any) -> Any:
    # Convertit "" -> None (SQLite)
    if v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


def _build_columns_map() -> List[Tuple[str, str]]:
    cols = get_table_columns(CLIENT_TABLE)

    # On enlève radical_compte car auto-généré par insert_client_if_new
    cols = [(c, t) for (c, t) in cols if c.lower() != "radical_compte"]

    return cols


def _guess_required_fields(cols: List[Tuple[str, str]]) -> List[str]:
    """
    On met en "required UI" les champs qu'on sait importants.
    Ton helper impose ID_Client, et toi tu as dit que num_tel/mail sont indispensables côté import;
    ici on les rend obligatoires si la colonne existe.
    """
    colset = {c for c, _ in cols}
    required = []
    if "ID_Client" in colset:
        required.append("ID_Client")
    if "Numero_Tel" in colset:
        required.append("Numero_Tel")
    if "Mail" in colset:
        required.append("Mail")
    return required


def _render_field(col: str, col_type: str, key: str) -> Any:
    """
    UI input selon un typage simple.
    - Numeric => number_input
    - Date-like => text_input (tu peux passer à date_input si tu veux standardiser)
    - Sinon => text_input
    """
    if _is_numeric_sqlite_type(col_type):
        return st.number_input(col, value=0.0, step=1.0, key=key)
    if _is_date_like(col_type):
        return st.text_input(col, value="", key=key, placeholder="YYYY-MM-DD ou texte")
    return st.text_input(col, value="", key=key)


def main(embedded: bool = False, key_prefix: str = "new_client") -> None:
    if not embedded:
        st.title("🆕 Formulaire nouveau client")

    cols = _build_columns_map()
    if not cols:
        st.error("Impossible de lire les colonnes de la table clients.")
        return

    required_fields = set(_guess_required_fields(cols))

    # Petite aide / rappel
    with st.expander("ℹ️ Règles", expanded=False):
        st.write("- `ID_Client` est obligatoire (sinon création refusée).")
        st.write("- `radical_compte` est généré automatiquement.")
        st.write("- Si `Numero_Tel` / `Mail` existent, on les force en obligatoire dans ce formulaire.")

    # Séparation : champs essentiels (top) + champs optionnels
    essentials = [c for c, _ in cols if c in required_fields]
    others = [c for c, _ in cols if c not in required_fields]

    # Form state init
    st.session_state.setdefault(f"{key_prefix}_values", {})

    with st.form(key=f"{key_prefix}_form", clear_on_submit=False):
        st.subheader("Champs essentiels")
        data: Dict[str, Any] = {}

        # Essentials (en 3 colonnes si possible)
        if essentials:
            ecols = st.columns(3)
            for i, col in enumerate(essentials):
                col_type = next((t for (c, t) in cols if c == col), "")
                with ecols[i % 3]:
                    v = _render_field(col, col_type, key=f"{key_prefix}_{col}")
                    data[col] = _normalize_value(v)

        st.divider()
        st.subheader("Champs optionnels")

        # Optionnels en grille (3 colonnes)
        ocols = st.columns(3)
        for i, col in enumerate(others):
            col_type = next((t for (c, t) in cols if c == col), "")
            with ocols[i % 3]:
                v = _render_field(col, col_type, key=f"{key_prefix}_{col}")
                data[col] = _normalize_value(v)

        # Boutons
        b1, b2 = st.columns([1, 1])
        with b1:
            submitted = st.form_submit_button("✅ Créer le client")
        with b2:
            reset = st.form_submit_button("🧹 Réinitialiser")

    if reset:
        # clear inputs
        for c, _ in cols:
            st.session_state.pop(f"{key_prefix}_{c}", None)
        st.rerun()

    if submitted:
        # Validation UI (en plus de ton helper)
        missing = []
        for f in required_fields:
            if not str(data.get(f) or "").strip():
                missing.append(f)

        if missing:
            st.error(f"Champs obligatoires manquants : {', '.join(missing)}")
            return

        ok, msg = insert_client_if_new(data)
        if ok:
            st.success(msg)
        else:
            st.error(msg)
