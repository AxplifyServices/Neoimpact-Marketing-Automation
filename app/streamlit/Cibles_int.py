from __future__ import annotations

import os
import sys
import json

import streamlit as st

# ✅ FIX: project root = .../ (racine du projet), pas .../app
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# =========================================================
# Import clients via fichier (STRICT)
# - Le fichier doit avoir EXACTEMENT les mêmes colonnes que la table clients
# - Colonnes obligatoires non nulles: ID_Client, Numero_Tel, Mail
# - Matching sur ID_Client:
#    - si existe -> update (sans toucher radical_compte)
#    - sinon -> insert + génération radical_compte
# =========================================================
REQUIRED_IMPORT_COLS = ["ID_Client", "Numero_Tel", "Mail"]

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
    list_campaigns_for_objective_filter_ui,
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
    "Nombre_transaction_inter",
    "Volume_transaction_inter",
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
    "App_instaled",
    "Premiere_connex",
    "carte_dispo_agence",
    "carte_retiree",
    "Carte_virtuelle",
    "Etudiant",
    "Dotation_touristique",
    "Dotation_ecom",
    "Compte_CIH_Mobile",
    "Compte_MAD_convertible",
    "MDM",
    "Presence_maroc",
    "BP",
    "chequier_dispo_agence",
    "chequier_retire",
    "chequier_active",
    "Nature_carte",
    "Categorie",
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
    "App_instaled": "App installée",
    "Premiere_connex": "Première connexion",
    "carte_dispo_agence": "Carte dispo agence",
    "carte_retiree": "Carte retirée",
    "Carte_virtuelle": "Carte virtuelle",
    "Etudiant": "Étudiant",
    "Dotation_touristique": "Dotation touristique",
    "Dotation_ecom": "Dotation e-commerce",
    "Compte_CIH_Mobile": "Compte CIH Mobile",
    "Compte_MAD_convertible": "Compte MAD convertible",
    "MDM": "MDM",
    "Presence_maroc": "Présence Maroc",
    "BP": "BP",
    "chequier_dispo_agence": "Chéquier dispo agence",
    "chequier_retire": "Chéquier retiré",
    "chequier_active": "Chéquier actif",
    "Nature_carte": "Nature de carte",
    "Categorie": "Catégorie client",
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
    "App_instaled": "App_instaled",
    "Premiere_connex": "Premiere_connex",
    "carte_dispo_agence": "carte_dispo_agence",
    "carte_retiree": "carte_retiree",
    "Carte_virtuelle": "Carte_virtuelle",
    "Etudiant": "Etudiant",
    "Dotation_touristique": "Dotation_touristique",
    "Dotation_ecom": "Dotation_ecom",
    "Compte_CIH_Mobile": "Compte_CIH_Mobile",
    "Compte_MAD_convertible": "Compte_MAD_convertible",
    "MDM": "MDM",
    "Presence_maroc": "Presence_maroc",
    "BP": "BP",
    "chequier_dispo_agence": "chequier_dispo_agence",
    "chequier_retire": "chequier_retire",
    "chequier_active": "chequier_active",
    "Nature_carte": "Nature_carte",
    "Categorie": "Categorie",
}

# =========================================================
# UI helpers
# =========================================================
def _fmt_lock_reason(reasons: dict, id_cible: str) -> str:
    if not reasons:
        return "Cette cible est liée à une campagne active/planifiée."
    return str(reasons.get(id_cible) or reasons.get(str(id_cible)) or "Cette cible est liée à une campagne active/planifiée.")


# =========================================================
# MAIN UI
# =========================================================
def main() -> None:
    st.title("🎯 Cibles")

    # Load list + locks
    cibles = list_cibles_for_ui()
    locked_ids, lock_reasons = get_locked_cibles_for_ui()
    locked_ids = set(str(x).strip() for x in (locked_ids or []))
    lock_reasons = lock_reasons or {}

    # Tabs
    tab_list, tab_create = st.tabs(["📋 Liste & aperçu", "➕ Créer / importer"])

    # =========================================================
    # LIST
    # =========================================================
    with tab_list:
        st.subheader("Liste des cibles")
        if not cibles:
            st.info("Aucune cible.")
        else:
            for c in cibles:
                cid = str(c.get("id_cible") or "").strip()
                nom = c.get("nom_cible") or ""
                src = c.get("source") or ""
                locked = cid in locked_ids

                cols = st.columns([0.12, 0.52, 0.18, 0.18], vertical_alignment="center")
                with cols[0]:
                    st.code(cid)
                with cols[1]:
                    st.write(f"**{nom}**")
                    st.caption(f"Source: {src}")
                    if locked:
                        st.warning(_fmt_lock_reason(lock_reasons, cid))
                with cols[2]:
                    if st.button("👁️ Aperçu", key=f"preview_{cid}"):
                        try:
                            df_head, total = preview_cible_for_ui(cid, limit=200)
                            st.success(f"{total} lignes")
                            st.dataframe(df_head, use_container_width=True, hide_index=True)
                        except Exception as e:
                            st.error(str(e))
                with cols[3]:
                    if locked:
                        st.button("🗑️ Supprimer", key=f"del_{cid}", disabled=True)
                    else:
                        if st.button("🗑️ Supprimer", key=f"del_{cid}"):
                            try:
                                delete_cible_for_ui(cid)
                                st.success("Supprimée ✅")
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))

        st.divider()

    # =========================================================
    # CREATE
    # =========================================================
    with tab_create:
        st.subheader("Créer une cible")

        mode = st.radio("Type de cible", ["DB", "Fichier plat"], horizontal=True)

        if mode == "DB":
            st.caption("Crée une cible à partir de filtres sur la base clients.")

            nom_cible = st.text_input("Nom de la cible", placeholder="Ex: Clients injoignables Région Casa")

            filtre = {}

            st.markdown("#### Filtres catégoriels")
            for field in CAT_FIELDS:
                label = FIELD_TO_LABEL.get(field, field)
                db_field = FIELD_TO_DB.get(field, field)

                values = get_distinct_values_for_ui(db_field)
                if not values:
                    continue

                sel = st.multiselect(label, values, key=f"cat_{field}")
                if sel:
                    filtre[db_field] = {"values": sel}

            st.markdown("#### Filtres numériques")
            for field in NUM_FIELDS:
                label = FIELD_TO_LABEL.get(field, field)
                db_field = FIELD_TO_DB.get(field, field)

                col1, col2 = st.columns(2)
                with col1:
                    min_val = st.number_input(f"{label} - min", value=0.0, step=1.0, key=f"min_{field}")
                with col2:
                    max_val = st.number_input(f"{label} - max", value=0.0, step=1.0, key=f"max_{field}")

                if max_val and max_val >= min_val:
                    filtre[db_field] = {"min": min_val, "max": max_val}

            st.markdown("#### Filtre objectif atteint dans une autre campagne")

            campagnes = list_campaigns_for_objective_filter_ui()
            campagne_options = {
                f"{c.get('nom_campagne') or c.get('id_campagne')} — {c.get('id_campagne')} [{c.get('etat')}]": c.get("id_campagne")
                for c in campagnes
            }

            selected_campaign_labels = st.multiselect(
                "Garder uniquement les clients ayant atteint un objectif dans ces campagnes",
                options=list(campagne_options.keys()),
                key="objectif_campagnes_filter",
            )

            selected_campaign_ids = [
                campagne_options[label]
                for label in selected_campaign_labels
                if campagne_options.get(label)
            ]

            if selected_campaign_ids:
                filtre["__objectif_campagnes__"] = {
                    "values": selected_campaign_ids
                }

            if st.button("✅ Créer la cible (DB)", type="primary"):
                try:
                    if not nom_cible.strip():
                        st.error("Nom de cible obligatoire.")
                    else:
                        create_cible_db_for_ui(nom_cible=nom_cible, filtre_dict=filtre)
                        st.success("Cible créée ✅")
                        st.rerun()
                except Exception as e:
                    st.error(str(e))

        else:
            st.caption("Crée une cible depuis un fichier (csv/xlsx/parquet/json).")

            nom_cible = st.text_input("Nom de la cible", placeholder="Ex: Prospect import Jan 2026")

            uploaded = st.file_uploader("Choisir un fichier", type=["csv", "xlsx", "xls", "parquet", "json"])

            path = ""
            if uploaded is not None:
                try:
                    path = save_uploaded_file_for_ui(uploaded)
                    st.success("Fichier uploadé ✅")
                    st.code(path)
                except Exception as e:
                    st.error(str(e))

            if path:
                with st.expander("ℹ️ Règles d’import (STRICT)", expanded=False):
                    st.markdown(
                        f"""- Le fichier doit respecter **exactement** la structure de la table `clients` (mêmes colonnes).
- Les colonnes **obligatoires** (non nulles) sont : **{', '.join(REQUIRED_IMPORT_COLS)}**.
- Matching en base via **ID_Client** :
  - si `ID_Client` existe → **mise à jour** (sans toucher `radical_compte`)
  - si `ID_Client` n'existe pas → **ajout** avec génération d’un `radical_compte` unique
"""
                    )

                if st.button("📥 Importer / Mettre à jour clients (optionnel)"):
                    try:
                        ins, upd = import_leads_into_clients_for_ui(path)
                        st.success(f"Import terminé ✅ Insert={ins} | Update={upd}")
                    except Exception as e:
                        st.error(str(e))

                if st.button("✅ Créer la cible (Fichier plat)", type="primary"):
                    try:
                        # ✅ auto-update clients (STRICT)
                        ins, upd = import_leads_into_clients_for_ui(path)
                        st.info(f"Base clients mise à jour: Insert={ins} | Update={upd}")

                        # ✅ puis création cible
                        create_cible_file_for_ui(nom_cible=nom_cible, file_path=path)
                        st.success("Cible créée ✅")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))


if __name__ == "__main__":
    main()
