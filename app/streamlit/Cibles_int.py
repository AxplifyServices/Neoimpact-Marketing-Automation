from __future__ import annotations

import os
import sys
import json

import streamlit as st

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ✅ Façade UI (plus de storage/sqlite/pandas dans le front)
from app.domain.ui_facades.cibles_ui_facade import (
    list_cibles_for_ui,
    get_locked_cibles_for_ui,
    get_cible_filtre_dict_for_ui,
    get_distinct_values_for_ui,
    save_uploaded_file_for_ui,
    import_leads_into_clients_for_ui,
    create_cible_db_for_ui,
    create_cible_file_for_ui,
    update_cible_for_ui,
    delete_cible_for_ui,
    preview_cible_for_ui,
)

# =========================================================
# Champs / mapping (EXISTANT)
# =========================================================
NUM_FIELDS = [
    "Age",
    "Anciennete",
    # KPIs / volumes
    "nb_transaction",
    "vol_transaction",
    "nb_retrait_gab",
    "vol_retrait_gab",
    "nb_transaction_ecom",
    "vol_transaction_ecom",
    "nb_virement",
    "vol_virement",
    "solde_moyen_depots",
    "encours_moyen",
    "encours_global",
    "encours_conso",
    "encours_immo",
    "montant_revenu",
]

CAT_FIELDS = [
    # existant
    "STATUT_CLIENT",
    "Dossier_complet",
    "Validation_KYC",
    "Activation_carte",
    # nouveaux champs éligibles
    "Canal_acquisition",
    "Qualite",
    "Region",
    "Agence",
    "Gestionnaire",
    "Activation_du_compte",
    "Segment_actuel",
    "Epargne",
    "Carte_Actuelle",
    "Assurance_Actuelle",
    "revenu_domicilie",
]

FIELD_LABELS = {
    # existant
    "STATUT_CLIENT": "Statut client",
    "Dossier_complet": "Dossier complet",
    "Validation_KYC": "Validation KYC",
    "Activation_carte": "Activation carte",
    "Age": "Age",
    "Anciennete": "Anciennete",
    # nouveaux (UI)
    "Canal_acquisition": "Canal acquisition",
    "Qualite": "Qualite",
    "Region": "Region",
    "Agence": "Agence",
    "Gestionnaire": "Gestionnaire",
    "Activation_du_compte": "Activation du compte",
    "Segment_actuel": "Segment actuel",
    "Epargne": "Epargne",
    "Carte_Actuelle": "Carte actuelle",
    "Assurance_Actuelle": "Assurance actuelle",
    "nb_transaction": "Nombre de transaction",
    "vol_transaction": "Volume de transaction",
    "nb_retrait_gab": "Nombre de retrait GAB",
    "vol_retrait_gab": "Volume de retrait GAB",
    "nb_transaction_ecom": "Nombre transaction e-com",
    "vol_transaction_ecom": "Volume transaction e-com",
    "nb_virement": "Nombre de virement",
    "vol_virement": "Volume de virement",
    "solde_moyen_depots": "Solde moyen des dépots",
    "encours_moyen": "Encours moyen",
    "encours_global": "Encours global",
    "encours_conso": "Encours Conso",
    "encours_immo": "Encours Immo",
    "revenu_domicilie": "Revenu domicilié",
    "montant_revenu": "Montant revenu",
}

LABEL_TO_FIELD = {v: k for k, v in FIELD_LABELS.items()}
FIELD_TO_LABEL = FIELD_LABELS

FIELD_TO_DB = {
    # existant
    "STATUT_CLIENT": "STATUT_CLIENT",
    "Dossier_complet": "Dossier_Complet",
    "Validation_KYC": "Validation_KYC",
    "Activation_carte": "Activation_carte",
    "Age": "Age",
    "Anciennete": "Anciennete",
    # nouveaux champs (colonne SQL)
    "Canal_acquisition": "Canal_acquisition",
    "Qualite": "Qualite",
    "Region": "Region",
    "Agence": "Agence",
    "Gestionnaire": "Gestionnaire",
    "Activation_du_compte": "Activation_du_compte",
    "Segment_actuel": "Segment_actuel",
    "Epargne": "Epargne",
    "Carte_Actuelle": "Carte_Actuelle",
    "Assurance_Actuelle": "Assurance_Actuelle",
    "nb_transaction": "nb_transaction",
    "vol_transaction": "vol_transaction",
    "nb_retrait_gab": "nb_retrait_gab",
    "vol_retrait_gab": "vol_retrait_gab",
    "nb_transaction_ecom": "nb_transaction_ecom",
    "vol_transaction_ecom": "vol_transaction_ecom",
    "nb_virement": "nb_virement",
    "vol_virement": "vol_virement",
    "solde_moyen_depots": "solde_moyen_depots",
    "encours_moyen": "encours_moyen",
    "encours_global": "encours_global",
    "encours_conso": "encours_conso",
    "encours_immo": "encours_immo",
    "revenu_domicilie": "revenu_domicilie",
    "montant_revenu": "montant_revenu",
}

DB_TO_FIELD = {v: k for k, v in FIELD_TO_DB.items()}


# =========================================================
# Etat filtres UI (EXISTANT)
# =========================================================
def _ensure_filter_state():
    if "cible_filters_list" not in st.session_state:
        st.session_state.cible_filters_list = []


def _filters_list() -> list[dict]:
    _ensure_filter_state()
    ret = st.session_state.cible_filters_list
    if not isinstance(ret, list):
        ret = []
        st.session_state.cible_filters_list = ret
    return ret


def _set_filters_list(v: list[dict]) -> None:
    st.session_state.cible_filters_list = v


def _field_kind(field: str) -> str:
    if field in NUM_FIELDS:
        return "numeric"
    return "categorical"


def _filters_list_to_dict(filters_list: list[dict]) -> dict:
    out: dict = {}
    for f in filters_list:
        field = str(f.get("field", "")).strip()
        if not field:
            continue
        kind = f.get("kind") or _field_kind(field)

        if kind == "numeric":
            mn = f.get("min", None)
            mx = f.get("max", None)
            if mn is None and mx is None:
                continue
            payload = {}
            if mn is not None:
                payload["min"] = int(mn)
            if mx is not None:
                payload["max"] = int(mx)
            if payload:
                out[field] = payload
        else:
            vals = f.get("values") or []
            vals = [str(x) for x in vals if str(x).strip() != ""]
            if vals:
                out[field] = {"values": vals}
    return out


# ✅ dict (DB) -> liste builder (UI)
def _filtre_dict_to_filters_list(filtre: dict) -> list[dict]:
    out: list[dict] = []
    if not isinstance(filtre, dict):
        return out

    for field, payload in filtre.items():
        if not isinstance(payload, dict):
            continue

        # numeric
        if ("min" in payload) or ("max" in payload):
            mn = payload.get("min", None)
            mx = payload.get("max", None)
            out.append({"field": field, "kind": "numeric", "min": mn, "max": mx})
            continue

        # categorical
        if "values" in payload:
            vals = payload.get("values") or []
            out.append({"field": field, "kind": "categorical", "values": vals})
            continue

    return out


def _render_filters_panel():
    _ensure_filter_state()
    filters_list = _filters_list()

    all_fields = NUM_FIELDS + CAT_FIELDS

    selected_field = st.selectbox("Variable", options=all_fields, key="cible_filter_selected_field")
    kind = _field_kind(selected_field)
    st.write(f"Type: **{kind}**")

    existing = None
    idx = None
    for i, f in enumerate(filters_list):
        if f.get("field") == selected_field:
            existing = f
            idx = i
            break

    if kind == "numeric":
        mn0 = "" if not existing else ("" if existing.get("min") is None else str(existing.get("min")))
        mx0 = "" if not existing else ("" if existing.get("max") is None else str(existing.get("max")))

        mn_txt = st.text_input("Min", value=mn0, key="cible_filter_min")
        mx_txt = st.text_input("Max", value=mx0, key="cible_filter_max")

        btns = st.columns([1, 1, 2])
        if btns[0].button("➕ Ajouter / Mettre à jour", use_container_width=True):
            mn = None
            mx = None
            if str(mn_txt).strip() != "":
                mn = int(float(mn_txt))
            if str(mx_txt).strip() != "":
                mx = int(float(mx_txt))

            payload = {"field": selected_field, "kind": "numeric", "min": mn, "max": mx}
            if existing is None:
                filters_list.append(payload)
            else:
                filters_list[idx] = payload
            _set_filters_list(filters_list)
            st.rerun()

        if btns[1].button("🗑️ Supprimer", use_container_width=True):
            if existing is None:
                st.info("Aucun filtre à supprimer pour cette variable.")
            else:
                filters_list.pop(idx)
                _set_filters_list(filters_list)
                st.rerun()

    else:
        sql_col = FIELD_TO_DB.get(selected_field)
        if not sql_col:
            st.error(f"Variable '{selected_field}' non mappée à une colonne SQL.")
            return

        # ✅ distinct values via façade (plus d'accès direct storage)
        options = get_distinct_values_for_ui(sql_col)
        if not options:
            st.warning("Aucune valeur disponible en base pour cette variable.")

        default_vals = [] if not existing else (existing.get("values") or [])
        selected_values = st.multiselect("Valeurs", options=options, default=default_vals, key="cible_filter_values")

        btns = st.columns([1, 1, 2])
        if btns[0].button("➕ Ajouter / Mettre à jour", use_container_width=True):
            if not selected_values:
                st.warning("Sélectionne au moins une valeur.")
                st.stop()

            payload = {"field": selected_field, "kind": "categorical", "values": selected_values}
            if existing is None:
                filters_list.append(payload)
            else:
                filters_list[idx] = payload
            _set_filters_list(filters_list)
            st.rerun()

        if btns[1].button("🗑️ Supprimer", use_container_width=True):
            if existing is None:
                st.info("Aucun filtre à supprimer pour cette variable.")
            else:
                filters_list.pop(idx)
                _set_filters_list(filters_list)
                st.rerun()

    st.divider()
    st.write("**Filtres actuels**")
    if not filters_list:
        st.info("Aucun filtre.")
    else:
        for f in filters_list:
            with st.container(border=True):
                st.write(f"**{FIELD_TO_LABEL.get(f.get('field',''), f.get('field',''))}**")
                if (f.get("kind") or _field_kind(f.get("field",""))) == "numeric":
                    st.caption(f"min: {f.get('min', '—')} | max: {f.get('max', '—')}")
                else:
                    vv = f.get("values") or []
                    st.caption(f"{len(vv)} modalité(s)")
                    st.write(", ".join([str(x) for x in vv]) if vv else "—")


# =========================================================
# MAIN
# =========================================================
def main():
    st.title("Cibles")

    if "show_create_cibles" not in st.session_state:
        st.session_state.show_create_cibles = False

    # =========================
    # CREATE BUTTON
    # =========================
    col_a, col_b = st.columns([1, 6])
    with col_a:
        if st.button("➕", use_container_width=True):
            st.session_state.show_create_cibles = not st.session_state.show_create_cibles
    with col_b:
        st.caption("Créer une nouvelle cible")

    # =========================
    # CREATE
    # =========================
    if st.session_state.show_create_cibles:
        with st.container(border=True):
            st.subheader("Créer une cible")

            nom_cible = st.text_input("Nom de la cible", key="cible_nom")
            source = st.selectbox("Source", ["DB", "Fichier plat"], key="cible_source")

            st.divider()

            if source == "DB":
                st.write("Configurer les filtres de la cible (source DB).")

                if hasattr(st, "popover"):
                    with st.popover("Filtres"):
                        _render_filters_panel()
                else:
                    with st.expander("Filtres", expanded=False):
                        _render_filters_panel()

                if st.button("✅ Créer la cible (DB)", type="primary"):
                    try:
                        filtre_dict = _filters_list_to_dict(_filters_list())
                        create_cible_db_for_ui(nom_cible=nom_cible, filtre_dict=filtre_dict)

                        st.success("Cible créée ✅")
                        st.session_state.show_create_cibles = False
                        st.session_state.cible_filters_list = []
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            else:
                st.write("Importer un fichier plat (csv/xlsx/parquet).")
                uploaded = st.file_uploader("Choisir un fichier", type=["csv", "xlsx", "xls", "parquet"])

                path = ""
                if uploaded is not None:
                    try:
                        path = save_uploaded_file_for_ui(uploaded)
                        st.success("Fichier uploadé ✅")
                        st.code(path)
                    except Exception as e:
                        st.error(str(e))

                if path:
                    if st.button("📥 Importer dans clients (optionnel)"):
                        try:
                            ins, upd = import_leads_into_clients_for_ui(path)
                            st.success(f"Import terminé ✅ Insert={ins} | Update={upd}")
                        except Exception as e:
                            st.error(str(e))

                    if st.button("✅ Créer la cible (Fichier plat)", type="primary"):
                        try:
                            create_cible_file_for_ui(nom_cible=nom_cible, file_path=path)
                            st.success("Cible créée ✅")
                            st.session_state.show_create_cibles = False
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

            if st.button("❌ Annuler"):
                st.session_state.show_create_cibles = False
                st.rerun()

    st.divider()

    # =========================
    # LIST
    # =========================
    cibles = list_cibles_for_ui()
    st.subheader(f"Liste des cibles ({len(cibles)})")

    if not cibles:
        st.info("Aucune cible pour le moment.")
        return

    locked_cible_ids, locked_cible_reason = get_locked_cibles_for_ui()

    for row in cibles:
        with st.container(border=True):
            left, mid, right = st.columns([6, 2, 2])

            cid = str(row.get("id_cible", "")).strip()
            nom = row.get("nom_cible", "")
            source = row.get("source", "")
            date = row.get("date_creation", "")

            left.write(f"**{nom}** — `{cid}`")
            left.caption(f"Source: {source} | Créée le: {date}")

            with mid:
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("🔎 Détails", key=f"detail_{cid}", use_container_width=True):
                        st.session_state[f"show_detail_{cid}"] = not st.session_state.get(f"show_detail_{cid}", False)
                with b2:
                    if st.button(
                        "✏️ Modifier",
                        key=f"edit_{cid}",
                        use_container_width=True,
                        disabled=(cid in locked_cible_ids),
                    ):
                        to_open = not st.session_state.get(f"show_edit_{cid}", False)
                        st.session_state[f"show_edit_{cid}"] = to_open

                        if to_open and str(source).strip() == "DB":
                            filtre_dict = get_cible_filtre_dict_for_ui(row)
                            st.session_state.cible_filters_list = _filtre_dict_to_filters_list(filtre_dict)

                        st.rerun()

            with right:
                locked = cid in locked_cible_ids
                if st.button("🗑️ Supprimer", key=f"del_{cid}", use_container_width=True, disabled=locked):
                    try:
                        delete_cible_for_ui(cid)
                        st.success("Cible supprimée.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

                if locked:
                    st.caption(f"🔒 {locked_cible_reason.get(cid, 'Liée à une campagne active/planifiée')}")

            # =========================================================
            # ✏️ EDITION (SANS JSON)
            # =========================================================
            if st.session_state.get(f"show_edit_{cid}", False):
                st.divider()
                st.subheader(f"✏️ Modifier la cible : {nom} ({cid})")

                source_cur = str(source or "").strip()
                new_nom = st.text_input("Nom de la cible", value=str(nom or ""), key=f"edit_nom_{cid}")

                if source_cur == "DB":
                    st.caption("Filtres (édition) — même interface que la création")
                    if hasattr(st, "popover"):
                        with st.popover("Filtres"):
                            _render_filters_panel()
                    else:
                        with st.expander("Filtres", expanded=True):
                            _render_filters_panel()

                    filtre_dict = _filters_list_to_dict(_filters_list())
                    chemin_new = ""

                else:
                    current_path = (row.get("chemin") or "").strip()
                    up = st.file_uploader(
                        "Uploader un nouveau fichier (optionnel)",
                        type=["csv", "xlsx", "xls", "parquet"],
                        key=f"edit_upload_{cid}",
                    )
                    if up is not None:
                        try:
                            chemin_new = save_uploaded_file_for_ui(up)
                            st.success("Fichier sauvegardé ✅")
                        except Exception as e:
                            st.error(str(e))
                            chemin_new = current_path
                    else:
                        chemin_new = st.text_input("Chemin fichier", value=current_path, key=f"edit_path_{cid}")

                    filtre_dict = {}

                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button(
                        "💾 Enregistrer",
                        type="primary",
                        key=f"edit_save_{cid}",
                        use_container_width=True,
                        disabled=(cid in locked_cible_ids),
                    ):
                        try:
                            update_cible_for_ui(
                                id_cible=cid,
                                nom_cible=new_nom,
                                source=source_cur,
                                date_creation=str(row.get("date_creation") or ""),
                                filtre_dict=filtre_dict if source_cur == "DB" else {},
                                chemin=chemin_new if source_cur != "DB" else "",
                            )
                            st.success("Cible mise à jour ✅")
                            st.session_state[f"show_edit_{cid}"] = False
                            st.session_state.cible_filters_list = []
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

                with col_cancel:
                    if st.button("❌ Annuler", key=f"edit_cancel_{cid}", use_container_width=True):
                        st.session_state[f"show_edit_{cid}"] = False
                        st.session_state.cible_filters_list = []
                        st.rerun()

            # =========================================================
            # DETAILS + VISU
            # =========================================================
            if st.session_state.get(f"show_detail_{cid}", False):
                st.divider()

                filtre = get_cible_filtre_dict_for_ui(row)

                st.write("**Détails**")
                st.write(f"- ID: `{cid}`")
                st.write(f"- Nom: {nom}")
                st.write(f"- Source: {source}")

                if source == "DB":
                    st.write("**Filtres (DB)**")
                    if not filtre:
                        st.info("Aucun filtre.")
                    else:
                        for k, v in filtre.items():
                            with st.container(border=True):
                                st.write(f"**{k}**")
                                if isinstance(v, dict) and "values" in v:
                                    vals = v.get("values") or []
                                    st.caption(f"{len(vals)} modalité(s)")
                                    st.write(", ".join([str(x) for x in vals]) if vals else "—")
                                elif isinstance(v, dict):
                                    st.caption(f"min: {v.get('min', '—')} | max: {v.get('max', '—')}")
                                else:
                                    st.caption("—")

                else:
                    path = (row.get("chemin") or "").strip()
                    st.write("**Chemin fichier**")
                    st.code(path or "—")

                st.divider()
                st.write("**Visualiser la cible**")

                limit = st.number_input(
                    "Limite d'affichage",
                    min_value=10,
                    max_value=20000,
                    value=200,
                    step=10,
                    key=f"lim_{cid}",
                )

                if st.button("👁️ Visualiser", key=f"view_{cid}"):
                    try:
                        df_head, total = preview_cible_for_ui(cid, int(limit))
                        st.success(f"Affichage : {total} ligne(s)")
                        st.dataframe(df_head, use_container_width=True)
                    except Exception as e:
                        st.error(str(e))


if __name__ == "__main__":
    main()
