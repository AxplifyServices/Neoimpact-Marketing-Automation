from __future__ import annotations

import os
import sys
import json
import sqlite3
import pandas as pd
import streamlit as st

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.domain.cible import Cible
from app.storage.cibles_store_sqlite import (
    ensure_cibles_table,
    list_cibles,
    insert_cible,
    delete_cible,
    save_uploaded_file,
    import_leads_into_clients,
    get_distinct_values_clients,
)
from app.storage.campagnes_store_sqlite import list_campagnes_active  # ✅ NEW


DB_PATH = os.path.join(PROJECT_ROOT, "clients.db")

NUM_FIELDS = ["Age", "Ancienneté"]

CAT_FIELDS = [
    "Statut client",
    "Qualité",
    "Région",
    "Agence",
    "Segment actuel",
    "Dossier Complet",
    "Validation KYC",
    "Activation du compte",
    "Activation carte",
    "Canal d'acquisition",
    "Epargne",
    "Carte Actuelle",
    "Assurance Actuelle",
]

QUALITATIVE_FIELD_TO_COLUMN = {
    "Statut client": "STATUT_CLIENT",
    "Qualité": "Qualite",
    "Région": "Region",
    "Agence": "Agence",
    "Segment actuel": "Segment_actuel",
    "Dossier Complet": "Dossier_Complet",
    "Validation KYC": "Validation_KYC",
    "Activation du compte": "Activation_du_compte",
    "Activation carte": "Activation_carte",
    "Canal d'acquisition": "Canal_acquisition",
    "Epargne": "Epargne",
    "Carte Actuelle": "Carte_Actuelle",
    "Assurance Actuelle": "Assurance_Actuelle",
}

NUM_FIELD_TO_COLUMN = {
    "Age": "Age",
    "Ancienneté": "Anciennete",
}


def _read_flat_file(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower().strip(".")
    if ext == "csv":
        return pd.read_csv(path)
    if ext in ("xlsx", "xls"):
        return pd.read_excel(path, sheet_name=0)
    if ext == "json":
        return pd.read_json(path)
    if ext == "parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Format non supporté: .{ext}")


def _query_clients_by_filtre(filtre_dict: dict, limit: int = 200) -> pd.DataFrame:
    where = []
    params = []

    for k, v in (filtre_dict or {}).items():
        if k in NUM_FIELDS and isinstance(v, dict):
            col = NUM_FIELD_TO_COLUMN.get(k)
            if not col:
                continue
            minv = v.get("min", None)
            maxv = v.get("max", None)
            if minv is not None:
                where.append(f"{col} >= ?")
                params.append(int(minv))
            if maxv is not None:
                where.append(f"{col} <= ?")
                params.append(int(maxv))

    for k, v in (filtre_dict or {}).items():
        if k in CAT_FIELDS and isinstance(v, dict):
            col = QUALITATIVE_FIELD_TO_COLUMN.get(k)
            if not col:
                continue
            values = v.get("values", [])
            if values:
                placeholders = ",".join(["?"] * len(values))
                where.append(f"{col} IN ({placeholders})")
                params.extend(values)

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    sql = f"SELECT * FROM clients{where_sql} LIMIT {int(limit)}"

    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()

    return df


def main():
    st.set_page_config(page_title="Cibles", layout="wide")
    ensure_cibles_table()

    st.title("🎯 Cibles")

    top = st.columns([6, 1])

    # ✅ FIX: init correct de la clé
    if "show_create_cibles" not in st.session_state:
        st.session_state.show_create_cibles = False

    if top[1].button("➕", use_container_width=True):
        st.session_state.show_create_cibles = not st.session_state.show_create_cibles

    # =========================
    # CREATE
    # =========================
    if st.session_state.show_create_cibles:
        with st.container(border=True):
            st.subheader("Créer une cible")
            nom_cible = st.text_input("Nom de la cible", value="").strip()

            source_ui = st.radio(
                "Source",
                ["Depuis la base de données", "Depuis un fichier plat"],
                horizontal=True,
            )

            if source_ui == "Depuis la base de données":
                st.markdown("### Filtres")

                if "cible_filtre" not in st.session_state:
                    st.session_state.cible_filtre = {}
                filtre = st.session_state.cible_filtre

                ALL_FIELDS = NUM_FIELDS + CAT_FIELDS
                selected = st.selectbox("Variable", options=["-- choisir --"] + ALL_FIELDS)

                if selected != "-- choisir --":
                    if selected in NUM_FIELDS:
                        c1, c2 = st.columns(2)
                        minv = c1.number_input("Min", step=1, value=int(filtre.get(selected, {}).get("min", 0)))
                        maxv = c2.number_input("Max", step=1, value=int(filtre.get(selected, {}).get("max", 100)))

                        if st.button("➕ Ajouter / Mettre à jour", key=f"add_{selected}"):
                            filtre[selected] = {"min": int(minv), "max": int(maxv)}
                            st.rerun()
                    else:
                        sql_col = QUALITATIVE_FIELD_TO_COLUMN.get(selected)
                        if not sql_col:
                            st.error(f"Variable '{selected}' non mappée à une colonne SQL.")
                        else:
                            options = get_distinct_values_clients(sql_col)
                            if not options:
                                st.warning("Aucune valeur disponible en base pour cette variable.")

                            selected_values = st.multiselect(
                                "Valeurs",
                                options=options,
                                default=filtre.get(selected, {}).get("values", []),
                            )

                            if st.button("➕ Ajouter / Mettre à jour", key=f"add_{selected}"):
                                if selected_values:
                                    filtre[selected] = {"values": selected_values}
                                else:
                                    filtre.pop(selected, None)
                                st.rerun()

                st.markdown("#### Filtres actifs")
                if not filtre:
                    st.info("Aucun filtre ajouté.")
                else:
                    for k in list(filtre.keys()):
                        a, b = st.columns([8, 1])
                        a.write(f"**{k}** : {filtre[k]}")
                        if b.button("🗑️", key=f"rm_{k}"):
                            filtre.pop(k, None)
                            st.rerun()

                if st.button("🧹 Réinitialiser les filtres"):
                    st.session_state.cible_filtre = {}
                    st.rerun()

                if st.button("✅ Créer la cible (DB)", type="primary"):
                    try:
                        c = Cible(
                            id_cible="",
                            nom_cible=nom_cible,
                            source="DB",
                            filtre=st.session_state.cible_filtre,
                            chemin="",
                        )
                        new_id = insert_cible(c)
                        st.session_state.cible_filtre = {}
                        st.session_state.show_create_cibles = False
                        st.success(f"Cible créée: {new_id}")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            else:
                st.markdown("### Import fichier plat (csv/xlsx/json/parquet)")
                up = st.file_uploader("Drag & drop ton fichier", type=["csv", "xlsx", "xls", "json", "parquet"])

                saved_path = ""
                if up is not None:
                    saved_path = save_uploaded_file(up)
                    st.info(f"Fichier sauvegardé: {saved_path}")

                    if st.button("📥 Importer les leads dans la base clients"):
                        try:
                            nb_added, nb_skipped = import_leads_into_clients(saved_path)
                            st.success(f"Import OK | Ajoutés={nb_added} | Ignorés={nb_skipped}")
                        except Exception as e:
                            st.error(str(e))

                if st.button("✅ Créer la cible (Fichier plat)", type="primary"):
                    try:
                        c = Cible(
                            id_cible="",
                            nom_cible=nom_cible,
                            source="Fichier plat",
                            filtre={},
                            chemin=saved_path,
                        )
                        new_id = insert_cible(c)
                        st.session_state.show_create_cibles = False
                        st.success(f"Cible créée: {new_id}")
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
    cibles = list_cibles()
    st.subheader(f"Liste des cibles ({len(cibles)})")

    if not cibles:
        st.info("Aucune cible pour le moment.")
        return

    active_camps = list_campagnes_active()
    locked_cible_ids = {str(c.get("id_cible", "")).strip() for c in active_camps if c.get("id_cible")}
    locked_cible_reason = {}
    for c in active_camps:
        cid = str(c.get("id_cible", "")).strip()
        if cid:
            locked_cible_reason[cid] = f"{c.get('id_campagne')} ({c.get('etat_campagne')})"

    for row in cibles:
        cid = row.get("id_cible", "") or ""
        is_locked = str(cid).strip() in locked_cible_ids

        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([1, 3, 2, 3, 1])
            c1.write(f"**{cid}**")
            c2.write(row.get("nom_cible", ""))
            c3.write(row.get("source", ""))
            c4.write(row.get("date_creation", ""))

            if c5.button(
                "🗑️",
                key=f"del_{cid}",
                disabled=is_locked,
                help=("Suppression impossible: cible utilisée par une campagne active." if is_locked else "Supprimer"),
            ):
                try:
                    delete_cible(cid)
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

            with st.expander("Détails"):
                if is_locked:
                    st.warning(f"Cible verrouillée: utilisée par la campagne {locked_cible_reason.get(str(cid).strip())}")

                st.write("**Filtre**")
                st.code(row.get("filtre", ""), language="json")
                st.write("**Chemin**")
                st.code(row.get("chemin", ""), language="text")

                limit = st.number_input(
                    "Nombre max de lignes à afficher",
                    min_value=50,
                    max_value=5000,
                    value=200,
                    step=50,
                    key=f"lim_{cid}",
                )

                if st.button("📊 Visualiser le tableau", key=f"view_{cid}"):
                    try:
                        if row.get("source") == "DB":
                            filtre_str = row.get("filtre", "") or "{}"
                            filtre_dict = json.loads(filtre_str) if filtre_str.strip() else {}
                            df = _query_clients_by_filtre(filtre_dict, limit=int(limit))
                            st.success(f"Affichage (DB) : {len(df)} ligne(s) (limité à {limit})")
                            st.dataframe(df, use_container_width=True)
                        else:
                            path = (row.get("chemin") or "").strip()
                            if not path or not os.path.exists(path):
                                st.error("Fichier introuvable sur le disque.")
                            else:
                                df = _read_flat_file(path)
                                st.success(f"Affichage (Fichier) : {len(df)} ligne(s)")
                                st.dataframe(df.head(int(limit)), use_container_width=True)
                    except Exception as e:
                        st.error(str(e))


if __name__ == "__main__":
    main()
