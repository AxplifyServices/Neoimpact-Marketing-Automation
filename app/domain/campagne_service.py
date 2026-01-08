from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Tuple

import pandas as pd

from app.storage.campagnes_store_sqlite import insert_campagne, update_etat
from app.storage.clients_campagnes_store_sqlite import bulk_insert_clients, set_clients_etat_for_campagne
from app.storage.cibles_store_sqlite import load_clients_df_for_cible
from app.storage.modele_store_sqlite import load_db as load_modeles_db


# variable du modèle -> colonne clients
MODELE_VAR_TO_CLIENT_COL = {
    "Dossier Complet": "Dossier_Complet",
    "Validation KYC": "Validation_KYC",
    "Activation du compte": "Activation_du_compte",
    "Activation carte": "Activation_carte",
    "STATUT_CLIENT": "STATUT_CLIENT",
    "Epargne": "Epargne",
    "Carte Actuelle": "Carte_Actuelle",
    "Assurance Actuelle": "Assurance_Actuelle",
}


def _today() -> date:
    return date.today()


def _today_iso() -> str:
    return _today().isoformat()


def _parse_date_iso(d: str) -> date:
    """
    Supporte 'YYYY-MM-DD' et aussi 'YYYY-MM-DDTHH:MM:SS...' (si jamais).
    """
    if not d:
        return _today()
    s = str(d).strip()
    # garde seulement la partie date
    s = s[:10]
    return date.fromisoformat(s)


def _normalize_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def _compute_etat_campaign(date_debut_iso: str) -> str:
    # ✅ robust: compare des objets date, pas des strings
    d0 = _parse_date_iso(date_debut_iso)
    return "Planifiée" if d0 > _today() else "En cours"


def _get_modele_row(id_modele: str) -> Dict[str, Any]:
    df = load_modeles_db()
    if df is None or df.empty:
        raise ValueError("Aucun modèle en base.")
    row = df[df["ID_MODELE"] == id_modele]
    if row.empty:
        raise ValueError(f"Modèle introuvable: {id_modele}")
    return row.iloc[0].to_dict()


def _get_first_action_from_modele(modele_row: Dict[str, Any]) -> Tuple[str, str]:
    raw = (modele_row.get("liste_action") or "").strip()
    actions = json.loads(raw) if raw else []
    if not actions:
        return "1", ""

    a1 = None
    for a in actions:
        if str(a.get("ID", "")).strip() == "1":
            a1 = a
            break
    if not a1:
        a1 = actions[0]

    return "1", _normalize_str(a1.get("Action", ""))


def create_campagne(
    nom_campagne: str,
    id_modele: str,
    id_cible: str,
    date_debut: str,
    date_fin: str,
) -> Dict[str, Any]:
    nom_campagne = (nom_campagne or "").strip()
    if not nom_campagne:
        raise ValueError("Nom campagne obligatoire")

    today = _today_iso()
    if str(date_debut) < today:
        raise ValueError("Date de début impossible dans le passé")
    if str(date_fin) < str(date_debut):
        raise ValueError("Date de fin ne peut pas être avant date de début")

    modele = _get_modele_row(id_modele)
    variable = _normalize_str(modele.get("variable_cible"))
    objectif = _normalize_str(modele.get("Objectif"))

    client_col = MODELE_VAR_TO_CLIENT_COL.get(variable)
    if not client_col:
        raise ValueError(f"Variable modèle non mappée: {variable}")

    df = load_clients_df_for_cible(id_cible)
    if df is None or df.empty:
        raise ValueError("Cible vide")

    if "radical_compte" not in df.columns:
        raise ValueError("Cible: colonne 'radical_compte' manquante")
    if client_col not in df.columns:
        raise ValueError(f"Cible: colonne '{client_col}' absente (source fichier plat ?).")

    # Filtrage: retirer ceux déjà à l'objectif
    obj_u = objectif.strip().upper()
    df["_val"] = df[client_col].astype(str).str.strip().str.upper()
    df_keep = df[df["_val"] != obj_u].copy()

    # ✅ état campagne robust
    etat = _compute_etat_campaign(date_debut)

    id_campagne = insert_campagne(
        nom_campagne=nom_campagne,
        id_modele=id_modele,
        id_cible=id_cible,
        date_debut=str(date_debut),
        date_fin=str(date_fin),
        etat_campagne=etat,
    )

    id_action, action = _get_first_action_from_modele(modele)

    rows: List[Dict[str, Any]] = []
    for _, r in df_keep.iterrows():
        rc = str(r["radical_compte"]).strip()
        if not rc:
            continue
        statut_initial = _normalize_str(r.get(client_col, ""))

        rows.append(
            {
                "ID_CAMPAGNE": id_campagne,
                "Radical_compte": rc,
                "statut_avant_campagne": statut_initial,
                "statut_actuel": statut_initial,

                # ✅ IMPORTANT: Etat client = Etat campagne (Planifiée / En cours)
                "Etat_campagne": etat,

                "NB_jour_campagne": 0,
                "ID_Action": str(id_action),
                "Action": action,
                "Last_action": "",
                "Resultat_last_action": "",
                "Date_last_action": "",
                "NB_jour_last_action": None,
                "NB_appel": None,
                "NB_sms": None,
                "NB_mail": None,
                "NB_message": None,
            }
        )

    bulk_insert_clients(rows)

    return {
        "id_campagne": id_campagne,
        "etat_campagne": etat,
        "nb_cible_initial": int(len(df)),
        "nb_apres_filtrage": int(len(df_keep)),
        "nb_inseres": int(len(rows)),
        "variable_modele": variable,
        "objectif_modele": objectif,
        "colonne_client": client_col,
    }


def annuler_campagne(id_campagne: str) -> None:
    update_etat(id_campagne, "Annulée")
    set_clients_etat_for_campagne(id_campagne, "Annulée")
