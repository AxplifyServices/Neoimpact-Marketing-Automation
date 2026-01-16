from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from app.storage import db


# =========================================================
# Helpers (type / UI)
# =========================================================

def _is_numeric_series(s: pd.Series) -> bool:
    try:
        return pd.api.types.is_numeric_dtype(s)
    except Exception:
        return False


def _to_float_or_none(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, str) and x.strip() == "":
        return None
    try:
        return float(x)
    except Exception:
        return None


def _reset_data_page_state_for_table(table: str) -> None:
    """
    Supprime uniquement l'état lié aux filtres & editor pour une table.
    """
    prefix_a = f"data__{table}__"
    keys = list(st.session_state.keys())
    for k in keys:
        if k.startswith(prefix_a):
            st.session_state.pop(k, None)


# =========================================================
# Gestion des filtres (state)
# =========================================================

def _filters_state_key(table: str) -> str:
    return f"data__{table}__filters"


def _get_filters(table: str) -> List[Dict[str, Any]]:
    """
    Retourne une liste de filtres "UI" (pas JSON affiché à l'écran).
    Format interne:
      {
        "id": "f1",
        "col": "NomCol",
        "kind": "numeric" | "categorical",
        "min": "..." (string),
        "max": "..." (string),
        "values": [..] (list[str])
      }
    """
    k = _filters_state_key(table)
    if k not in st.session_state:
        st.session_state[k] = []
    return st.session_state[k]


def _set_filters(table: str, filters: List[Dict[str, Any]]) -> None:
    st.session_state[_filters_state_key(table)] = filters


def _next_filter_id(filters: List[Dict[str, Any]]) -> str:
    used = {f.get("id") for f in filters}
    i = 1
    while True:
        fid = f"f{i}"
        if fid not in used:
            return fid
        i += 1


def _infer_kind_from_preview(df_preview: pd.DataFrame, col: str) -> str:
    if col not in df_preview.columns:
        return "categorical"
    return "numeric" if _is_numeric_series(df_preview[col]) else "categorical"


def _add_filter(table: str, df_preview: pd.DataFrame, default_col: str) -> None:
    filters = _get_filters(table)
    fid = _next_filter_id(filters)
    kind = _infer_kind_from_preview(df_preview, default_col)

    if kind == "numeric":
        filters.append({"id": fid, "col": default_col, "kind": "numeric", "min": "", "max": ""})
    else:
        filters.append({"id": fid, "col": default_col, "kind": "categorical", "values": []})

    _set_filters(table, filters)


def _remove_filter(table: str, fid: str) -> None:
    filters = _get_filters(table)
    filters = [f for f in filters if f.get("id") != fid]
    _set_filters(table, filters)


# =========================================================
# Construction des filtres DB (si read_table(filters=...) existe)
# =========================================================

def _build_db_filters_from_ui(
    table: str,
    ui_filters: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Construit le dict filters attendu par db.read_table(..., filters=...).
    On utilise db.ColumnFilter / db.NumericBounds si disponibles.
    """
    out: Dict[str, Any] = {}

    has_columnfilter = hasattr(db, "ColumnFilter")
    has_numericbounds = hasattr(db, "NumericBounds")

    for f in ui_filters:
        col = str(f.get("col", "")).strip()
        if not col:
            continue

        kind = f.get("kind")

        # numeric
        if kind == "numeric":
            mn = _to_float_or_none(f.get("min"))
            mx = _to_float_or_none(f.get("max"))
            if mn is None and mx is None:
                continue

            if has_columnfilter and has_numericbounds:
                out[col] = db.ColumnFilter(numeric=db.NumericBounds(min=mn, max=mx))  # type: ignore[attr-defined]
            else:
                # fallback "simple" si tes classes n'existent pas
                out[col] = {"numeric": {"min": mn, "max": mx}}

        # categorical
        elif kind == "categorical":
            vals = f.get("values") or []
            vals = [str(x) for x in vals if str(x).strip() != ""]
            if not vals:
                continue

            if has_columnfilter:
                out[col] = db.ColumnFilter(categorical=vals)  # type: ignore[attr-defined]
            else:
                out[col] = {"categorical": vals}

    return out


# =========================================================
# UI filtres (bouton + dropdown + add/remove)
# =========================================================

def _get_distinct_values_safe(table: str, df_preview: pd.DataFrame, col: str) -> List[str]:
    """
    Récupère les modalités:
      - si db.get_distinct_values existe, on l'utilise
      - sinon: fallback preview (limité)
    """
    if hasattr(db, "get_distinct_values"):
        try:
            vals = db.get_distinct_values(table, col, limit=250)  # type: ignore[attr-defined]
            return [str(v) for v in vals]
        except Exception:
            pass

    if col in df_preview.columns:
        s = df_preview[col].dropna().astype(str)
        vals = sorted(set(s.tolist()))
        return vals[:250]
    return []


def _render_filters_panel(table: str, columns: List[str], df_preview: pd.DataFrame) -> None:
    """
    Affiche le panneau des filtres (blocs).
    """
    ui_filters = _get_filters(table)

    # Ajouter un filtre
    col_add_1, col_add_2 = st.columns([2, 1])
    with col_add_1:
        default_col = st.selectbox(
            "Variable",
            options=columns,
            key=f"data__{table}__new_filter_col",
            label_visibility="collapsed",
        )
    with col_add_2:
        if st.button("Ajouter", use_container_width=True, key=f"data__{table}__btn_add_filter"):
            _add_filter(table, df_preview, default_col)
            st.rerun()

    if not ui_filters:
        st.info("Aucun filtre actif.")
        return

    st.divider()

    # Filtres existants (blocs)
    for f in ui_filters:
        fid = f.get("id", "")
        if not fid:
            continue

        with st.container(border=True):
            top_l, top_r = st.columns([5, 1])
            with top_l:
                # choix variable par filtre
                current_col = f.get("col") if f.get("col") in columns else columns[0]
                new_col = st.selectbox(
                    "Variable du filtre",
                    options=columns,
                    index=columns.index(current_col),
                    key=f"data__{table}__{fid}__col",
                    label_visibility="collapsed",
                )

                # si variable change => on réinitialise le filtre
                if new_col != current_col:
                    kind = _infer_kind_from_preview(df_preview, new_col)
                    if kind == "numeric":
                        f.clear()
                        f.update({"id": fid, "col": new_col, "kind": "numeric", "min": "", "max": ""})
                    else:
                        f.clear()
                        f.update({"id": fid, "col": new_col, "kind": "categorical", "values": []})
                    _set_filters(table, ui_filters)
                    st.rerun()

            with top_r:
                if st.button("🗑️", key=f"data__{table}__{fid}__delete", help="Supprimer ce filtre"):
                    _remove_filter(table, fid)
                    st.rerun()

            # Contenu filtre selon type
            colname = f.get("col")
            kind = f.get("kind") or _infer_kind_from_preview(df_preview, colname)

            if kind == "numeric":
                c1, c2 = st.columns(2)
                with c1:
                    mn = st.text_input(
                        "Min",
                        value=str(f.get("min", "")),
                        key=f"data__{table}__{fid}__min",
                        placeholder="(vide = pas de borne)",
                    )
                with c2:
                    mx = st.text_input(
                        "Max",
                        value=str(f.get("max", "")),
                        key=f"data__{table}__{fid}__max",
                        placeholder="(vide = pas de borne)",
                    )
                # sync state
                f["min"] = mn
                f["max"] = mx
                f["kind"] = "numeric"

            else:
                options = _get_distinct_values_safe(table, df_preview, colname)
                selected = st.multiselect(
                    "Modalités",
                    options=options,
                    default=f.get("values", []),
                    key=f"data__{table}__{fid}__values",
                )
                f["values"] = selected
                f["kind"] = "categorical"

    # sauver back state
    _set_filters(table, ui_filters)


# =========================================================
# Detect changes / autosave
# =========================================================

def _detect_changes(original: pd.DataFrame, edited: pd.DataFrame) -> List[Tuple[int, str, object]]:
    changes: List[Tuple[int, str, object]] = []
    if original.empty or edited.empty:
        return changes
    if "__rowid__" not in original.columns or "__rowid__" not in edited.columns:
        return changes

    o = original.set_index("__rowid__", drop=False)
    e = edited.set_index("__rowid__", drop=False)

    common_rowids = o.index.intersection(e.index)
    if len(common_rowids) == 0:
        return changes

    cols = [c for c in original.columns if c != "__rowid__"]

    for rid in common_rowids:
        for col in cols:
            ov = o.at[rid, col]
            nv = e.at[rid, col]
            try:
                if pd.isna(ov) and pd.isna(nv):
                    continue
            except Exception:
                pass
            if (ov == nv):
                continue
            changes.append((int(rid), col, nv))

    return changes


# =========================================================
# Main
# =========================================================

def main() -> None:
    st.title("Data")

    tables = db.list_tables()
    if not tables:
        st.warning("Aucune table trouvée.")
        return

    default_table = "clients_campagnes" if "clients_campagnes" in tables else tables[0]
    table = st.selectbox("Table", options=tables, index=tables.index(default_table), key="data__table_select")

    # reset state si table change
    last = st.session_state.get("data__last_table")
    if last != table:
        st.session_state["data__last_table"] = table
        _reset_data_page_state_for_table(table)
        # on reset aussi "new_filter_col" pour éviter incohérences
        st.session_state.pop(f"data__{table}__new_filter_col", None)
        st.rerun()

    # Preview (pour types & modalités)
    try:
        df_preview = db.read_table(table, filters=None, limit=500)  # si ton read_table supporte limit
    except TypeError:
        # fallback si ton read_table n'a pas limit
        df_preview = db.read_table(table, filters=None)

    if df_preview is None or df_preview.empty:
        st.info("Table vide.")
        return

    cols = [c for c in df_preview.columns if c != "__rowid__"]

    # Bouton Filtres -> panneau (popover si dispo, sinon expander)
    # Streamlit récent: st.popover existe. On fait fallback expander si non dispo.
    ui_filters = _get_filters(table)

    left, right = st.columns([1, 4])
    with left:
        if hasattr(st, "popover"):
            with st.popover("Filtres"):
                _render_filters_panel(table, cols, df_preview)
                st.divider()
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Réinitialiser", use_container_width=True, key=f"data__{table}__reset_filters"):
                        _set_filters(table, [])
                        st.rerun()
                with c2:
                    st.caption(f"{len(ui_filters)} filtre(s)")
        else:
            with st.expander("Filtres", expanded=False):
                _render_filters_panel(table, cols, df_preview)
                st.divider()
                if st.button("Réinitialiser", key=f"data__{table}__reset_filters"):
                    _set_filters(table, [])
                    st.rerun()

    # Construire filtres DB + lecture table filtrée
    db_filters = _build_db_filters_from_ui(table, _get_filters(table))

    try:
        df = db.read_table(table, filters=db_filters)
    except TypeError:
        # fallback si read_table ne supporte pas filters=...
        df = db.read_table(table)
        # (Dans ce cas, dis-moi et je te fais la version "filtrage pandas" propre)

    st.caption(f"{len(df)} ligne(s)")

    if df.empty:
        st.info("Aucune ligne ne correspond aux filtres.")
        return

    edited = st.data_editor(
        df,
        key=f"data__{table}__editor",
        disabled=["__rowid__"] if "__rowid__" in df.columns else [],
        hide_index=True,
        height=620,
    )

    changes = _detect_changes(df, edited)
    if changes:
        for rid, col, val in changes:
            db.update_cell(table, rid, col, val)
        st.success(f"{len(changes)} modification(s) enregistrée(s).")
        st.rerun()


if __name__ == "__main__":
    main()
