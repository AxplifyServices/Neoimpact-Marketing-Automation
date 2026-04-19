from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Tuple
import json
import re
import unicodedata
import sqlite3

import pandas as pd

from app.storage.db import DB_PATH
from app.storage.campagnes_store_sqlite import insert_campagne, update_etat
from app.storage.clients_campagnes_store_sqlite import (
    ensure_table as ensure_clients_campagnes_table,
    bulk_insert_clients,
    set_clients_etat_for_campagne,
)
from app.storage.cibles_store_sqlite import load_clients_df_for_cible
from app.storage.modele_store_sqlite import get_modele_dict

# NEW: échéance (arriv_eche)
from app.domain.workflow_nav import find_bloc_by_id, arrive_echeance  # retourne dict


# =========================================================
# Helpers
# =========================================================
def _norm_str(x: Any) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):  # type: ignore
            return ""
    except Exception:
        pass
    return str(x).strip()


def _norm_cmp(x: Any) -> str:
    """Normalisation robuste pour comparer des valeurs métier (casse/espaces/accents)."""
    s = _norm_str(x).lower()
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _infer_etat(date_debut: str, date_fin: str) -> str:
    """
    - today < debut  -> Planifiée
    - debut..fin     -> En cours
    - today > fin    -> Terminée
    """
    try:
        d0 = date.fromisoformat(_norm_str(date_debut)[:10])
        d1 = date.fromisoformat(_norm_str(date_fin)[:10])
    except Exception:
        return "Planifiée"

    today = date.today()
    if today < d0:
        return "Planifiée"
    if d0 <= today <= d1:
        return "En cours"
    return "Terminée"


def _detect_radical_col(df: pd.DataFrame) -> str:
    for c in ["Radical_compte", "radical_compte", "Radical compte", "radical compte"]:
        if c in df.columns:
            return c
    for c in df.columns:
        if "radical" in str(c).lower():
            return c
    return ""


def _detect_statut_col(df: pd.DataFrame) -> str | None:
    for c in ["STATUT_CLIENT", "statut_client", "Statut_client", "Statut Client", "statut client"]:
        if c in df.columns:
            return c
    for c in df.columns:
        if "statut" in str(c).lower():
            return c
    return None


def _remove_rupture_relation_strict(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """Exclure uniquement STATUT_CLIENT == 'Rupture de relation' (robuste)."""
    col = _detect_statut_col(df)
    if not col:
        return df, 0

    s = df[col].apply(_norm_cmp)
    mask = s.eq(_norm_cmp("Rupture de relation"))
    removed = int(mask.sum())
    return df.loc[~mask].copy(), removed


def _safe_json_loads(s: str, default):
    try:
        return json.loads(s)
    except Exception:
        return default


def _find_root_bloc(liste_action: list) -> dict | None:
    """
    NEW format:
      - root = bloc dont Parents est [] ou absent
    Fallback legacy:
      - Bloc_mere == 'oui'
      - ID == '1'
    """
    if not isinstance(liste_action, list) or not liste_action:
        return None

    # 1) NEW: Parents vide
    for b in liste_action:
        if not isinstance(b, dict):
            continue
        parents = b.get("Parents")
        if parents is None or (isinstance(parents, list) and len(parents) == 0):
            return b

    # 2) Legacy: Bloc_mere / Bloc_mère
    for b in liste_action:
        if isinstance(b, dict) and _norm_str(b.get("Bloc_mere")).lower() == "oui":
            return b

    # 3) Legacy fallback: ID==1
    for b in liste_action:
        if isinstance(b, dict) and _norm_str(b.get("ID")) == "1":
            return b

    return liste_action[0]


def _is_first_action_mail(canal_init: str, action_init: str) -> bool:
    """
    Dans ton projet: canal=Mail + action souvent = 'Message' (canaux.py).
    On accepte aussi action='Mail' pour robustesse.
    """
    c = _norm_str(canal_init)
    a = _norm_str(action_init)
    return (c == "Mail") and (a in ("Message", "Mail"))


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def _delete_outputs_for_campagne(id_campagne: str) -> Dict[str, int]:
    """
    Supprime les lignes liées à la campagne dans les tables CRC / CC / DA.
    Retourne les compteurs supprimés.
    """
    tables = {
        "crc": "crc_input",
        "cc": "vers_cc",
        "da": "vers_da",
        "cc_terrain": "vers_cc_terrain",
        "da_terrain": "vers_da_terrain",
    }

    deleted = {"crc": 0, "cc": 0, "da": 0, "cc_terrain": 0, "da_terrain": 0}

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        for k, t in tables.items():
            if not _table_exists(conn, t):
                continue
            cur.execute(f"SELECT COUNT(*) FROM {t} WHERE ID_CAMPAGNE = ?", (id_campagne,))
            n0 = cur.fetchone()[0] or 0
            cur.execute(f"DELETE FROM {t} WHERE ID_CAMPAGNE = ?", (id_campagne,))
            deleted[k] = int(n0)
        conn.commit()
        return deleted
    finally:
        conn.close()


def _extract_final_queue_routing(route_result: Dict[str, Any]) -> str:
    """
    route_after_update peut retourner:
      - routed_to: crc_input / vers_cc / vers_da / none
      - routed_to: mail + post_mail: {...}
    On veut compter la queue finale.
    """
    rt = (route_result or {}).get("routed_to") or ""
    rt = str(rt).strip()

    if rt == "mail":
        post = (route_result or {}).get("post_mail") or {}
        return _extract_final_queue_routing(post)

    return rt


def _route_initial_queues_for_campaign(id_campagne: str) -> Dict[str, int]:
    """
    Routage initial (métier) pour tous les clients de la campagne via contact_client_engine.route_after_update.
    Important: on nettoie les queues avant.
    """
    from app.engine.contact_client_engine import route_after_update

    # anti-doublons (sécurité)
    _delete_outputs_for_campagne(id_campagne)

    # liste des clients
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT Radical_compte
            FROM clients_campagnes
            WHERE ID_CAMPAGNE = ?
            """,
            (id_campagne,),
        )
        radicals = [str(r["Radical_compte"]).strip() for r in cur.fetchall() if str(r["Radical_compte"]).strip()]
    finally:
        conn.close()

    counts = {"crc": 0, "cc": 0, "da": 0, "cc_terrain": 0, "da_terrain": 0}

    for rc in radicals:
        res = route_after_update(id_campagne, rc)
        final_rt = _extract_final_queue_routing(res)

        if final_rt == "crc_input":
            counts["crc"] += 1
        elif final_rt == "vers_cc":
            counts["cc"] += 1
        elif final_rt == "vers_da":
            counts["da"] += 1
        elif final_rt == "vers_cc_terrain":
            counts["cc_terrain"] += 1
        elif final_rt == "vers_da_terrain":
            counts["da_terrain"] += 1

    return counts


# =========================================================
def create_campagne(
    nom_campagne: str,
    id_modele: str,
    id_cible: str,
    date_debut: str,
    date_fin: str,
    etat_campagne: str | None = None,
    description: str | None = None,
    type_campagne: str | None = None,
) -> Dict[str, Any]:
    """
    Crée campagne + peuple clients_campagnes.

    Règles appliquées à la création :
    - Exclure STATUT_CLIENT == 'Rupture de relation'
    - Si la campagne démarre "En cours":
        - si la première action est Mail => exécuter mail meta-loop immédiatement
        - puis router initialement vers CRC/CC/DA via route_after_update (métier)
    """

    # 0) Etat campagne
    if not etat_campagne:
        etat_campagne = _infer_etat(date_debut, date_fin)
    
    type_campagne = _norm_str(type_campagne) or "sans_action_terrain"
    if type_campagne not in ("sans_action_terrain", "avec_action_terrain"):
        raise ValueError("type_campagne invalide: sans_action_terrain | avec_action_terrain")

    # 1) Charger modèle (nouveau schéma / ancien toléré)
    modele = get_modele_dict(id_modele) or {}
    if not modele:
        raise ValueError(f"Modèle introuvable: {id_modele}")

    raw_liste = modele.get("liste_action") or "[]"
    if isinstance(raw_liste, list):
        liste_action = raw_liste
    else:
        try:
            liste_action = json.loads(str(raw_liste))
        except Exception:
            liste_action = []
    if not isinstance(liste_action, list):
        liste_action = []

    # graphe_json optionnel (pas utilisé ici)
    raw_graph = modele.get("graphe_json") or "{}"
    if isinstance(raw_graph, dict):
        graphe_json = raw_graph
    else:
        try:
            graphe_json = json.loads(str(raw_graph))
        except Exception:
            graphe_json = {}
    _ = graphe_json  # gardé pour compat/cohérence

    # 2) Root bloc (ID_Action/Canal/Action init)
    root = _find_root_bloc(liste_action) or {}

    id_action_init = _norm_str(root.get("ID")) or "1"
    canal_init = _norm_str(root.get("Canal")) or "Appel"
    action_init = _norm_str(root.get("Action")) or "Appeler"

    # Si le root est un bloc objectif => on force Canal/Action "Objectif"
    from app.domain.workflow_nav import is_objective_bloc
    if is_objective_bloc(root):
        canal_init = "Objectif"
        action_init = "Objectif"

    # Bloc courant initial (pour calcul arriv_eche)
    current_bloc_init = find_bloc_by_id(liste_action, id_action_init) or root

    # 3) Charger population cible
    df = load_clients_df_for_cible(id_cible)
    nb_init = int(len(df))

    # 4) Filtre rupture relation
    df, removed_rupture = _remove_rupture_relation_strict(df)
    nb_apres = int(len(df))

    # 6) Création campagne
    ensure_clients_campagnes_table()
    id_campagne = insert_campagne(
        nom_campagne=nom_campagne,
        id_modele=id_modele,
        id_cible=id_cible,
        date_debut=date_debut,
        date_fin=date_fin,
        etat_campagne=etat_campagne,
        description=description,
        type_campagne=type_campagne,
    )

    # 7) Préparer lignes clients_campagnes
    radical_col = _detect_radical_col(df)

    rows: List[Dict[str, Any]] = []
    today_iso = date.today().isoformat()

    for _, r in df.iterrows():
        rc = _norm_str(r.get(radical_col))
        if not rc:
            continue

        row_cc = {
            "Nom_campagne": nom_campagne,
            "ID_CAMPAGNE": id_campagne,
            "Radical_compte": rc,
            "Etat_campagne": etat_campagne,
            "NB_jour_campagne": 0,
            "ID_Action": id_action_init,
            "Canal": canal_init,
            "Action": action_init,
            "Last_action": "",
            "Resultat_last_action": "",
            "Date_last_action": today_iso,
            "NB_jour_last_action": 0,
            "NB_appel": 0,
            "NB_mail": 0,
            "NB_sms": 0,
            "NB_message": 0,
            "NB_approche_commercial": 0,
            "date_debut_campagne": _norm_str(date_debut)[:10],
            "nb_jour_debut_campagne": 0,
            "conversion": 0,
        }

        # arriv_eche : Oui/Non selon les conditions de type NB_jour_last_action dans les fils
        if _norm_str(row_cc.get("Etat_campagne")) not in ("En cours", "Planifiée", "En pause"):
            row_cc["arriv_eche"] = "Non"
        elif _norm_str(row_cc.get("Action")) == "Closed":
            row_cc["arriv_eche"] = "Non"
        else:
            row_cc["arriv_eche"] = arrive_echeance(liste_action, current_bloc_init, row_cc)

        rows.append(row_cc)

    # 8) Insert
    bulk_insert_clients(rows)

    # 9) Sync état campagne sur clients_campagnes
    set_clients_etat_for_campagne(id_campagne, etat_campagne)

    output_counts = {"crc": 0, "cc": 0, "da": 0, "cc_terrain": 0, "da_terrain": 0}
    mail_summary = None

    # 10) Si "En cours" uniquement: mails init puis routage métier (queues)
    if etat_campagne == "En cours":
        # (A) Si 1ère action = Mail => traiter immédiatement
        if _is_first_action_mail(canal_init, action_init):
            try:
                from app.engine.traitement_mail_engine import run_mail_meta_loop
                mail_summary = run_mail_meta_loop(max_passes=20, limit_rows_per_pass=9999)
            except Exception as e:
                mail_summary = {"error": "mail_meta_loop_failed", "details": str(e)}

        # (B) Routage initial (métier) vers CRC/CC/DA
        try:
            output_counts = _route_initial_queues_for_campaign(id_campagne)
        except Exception:
            output_counts = {"crc": 0, "cc": 0, "da": 0, "cc_terrain": 0, "da_terrain": 0}

    return {
        "id_campagne": id_campagne,
        "nb_cible_initial": nb_init,
        "nb_apres_filtrage": nb_apres,
        "nb_exclus_rupture": int(removed_rupture),
        "nb_clients_insérés": int(len(rows)),
        "etat_campagne": etat_campagne,
        "type_campagne": type_campagne,
        "id_action_initial": id_action_init,
        "canal_initial": canal_init,
        "action_initiale": action_init,
        "mail_meta_loop": mail_summary,
        "output_insert": output_counts,
    }


def annuler_campagne(id_campagne: str) -> Dict[str, Any]:
    """
    Annule une campagne et supprime automatiquement les lignes liées dans:
    - crc_input
    - vers_cc
    - vers_da
    """
    update_etat(id_campagne, "Annulée")
    set_clients_etat_for_campagne(id_campagne, "Annulée")

    deleted = {"crc": 0, "cc": 0, "da": 0, "cc_terrain": 0, "da_terrain": 0}
    try:
        deleted = _delete_outputs_for_campagne(id_campagne)
    except Exception as e:
        return {"id_campagne": id_campagne, "ok": False, "error": str(e), "deleted": deleted}

    return {"id_campagne": id_campagne, "ok": True, "deleted": deleted}


def _campagne_has_mail_action(id_campagne: str) -> bool:
    """
    True si au moins un client de la campagne a un bloc courant Mail (action Message/Mail),
    non Closed. (On ne vérifie pas l'envoi, juste la présence d'un besoin.)
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1
            FROM clients_campagnes
            WHERE ID_CAMPAGNE = ?
              AND COALESCE(Action,'') <> 'Closed'
              AND COALESCE(Canal,'') = 'Mail'
              AND COALESCE(Action,'') IN ('Message','Mail')
            LIMIT 1
            """,
            (id_campagne,),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def mettre_en_pause_campagne(id_campagne: str) -> Dict[str, Any]:
    """
    Met une campagne en pause:
    - campagne.etat = 'En pause'
    - clients_campagnes.Etat_campagne = 'En pause' (pour cette campagne)
    - supprime immédiatement les lignes de queues liées (crc_input / vers_cc / vers_da)
    """
    update_etat(id_campagne, "En pause")
    set_clients_etat_for_campagne(id_campagne, "En pause")

    deleted = {"crc": 0, "cc": 0, "da": 0, "cc_terrain": 0, "da_terrain": 0}
    try:
        deleted = _delete_outputs_for_campagne(id_campagne)
    except Exception as e:
        return {"id_campagne": id_campagne, "ok": False, "error": str(e), "deleted": deleted}

    return {"id_campagne": id_campagne, "ok": True, "etat": "En pause", "deleted": deleted}


def activer_campagne(id_campagne: str) -> Dict[str, Any]:
    """
    Réactive une campagne UNIQUEMENT si elle est actuellement en pause.
    - calcule le nouvel état selon dates:
        today < debut  -> Planifiée
        debut..fin     -> En cours
        today > fin    -> Terminée
    - met à jour campagne + clients_campagnes
    - si nouvel état = En cours:
        - supprime les anciennes queues de cette campagne
        - NEW: sync nouveaux clients depuis la cible (INSERT ONLY)
        - traite les mails si nécessaire (au moins un client a Canal=Mail)
        - route vers queues CRC/CC/DA via route_after_update (métier)
    - si Planifiée ou Terminée:
        - supprime les queues de cette campagne (sécurité)
        - ne remplit rien
    """
    from app.storage.campagnes_store_sqlite import get_campagne

    c = get_campagne(id_campagne) or {}
    etat_cur = _norm_str(c.get("etat") or c.get("etat_campagne"))

    if etat_cur != "En pause":
        return {
            "id_campagne": id_campagne,
            "ok": False,
            "error": f"Campagne non éligible à l'activation (etat actuel: {etat_cur or 'inconnu'}).",
        }

    date_debut = _norm_str(c.get("date_debut"))
    date_fin = _norm_str(c.get("date_fin"))

    new_etat = _infer_etat(date_debut, date_fin)

    # update etats
    update_etat(id_campagne, new_etat)
    set_clients_etat_for_campagne(id_campagne, new_etat)

    # nettoyer queues associées avant décision
    deleted = {"crc": 0, "cc": 0, "da": 0, "cc_terrain": 0, "da_terrain": 0}
    try:
        deleted = _delete_outputs_for_campagne(id_campagne)
    except Exception:
        pass

    mail_summary = None
    output_counts = {"crc": 0, "cc": 0, "da": 0, "cc_terrain": 0, "da_terrain": 0}
    new_clients_added = 0  # NEW

    if new_etat == "En cours":
        # NEW: sync nouveaux clients depuis la cible (INSERT ONLY) avant mail/rebuild
        try:
            id_cible = _norm_str(c.get("id_cible") or c.get("ID_CIBLE") or c.get("cible_id"))
            if id_cible:
                from app.scripts.batch_manuel import sync_new_clients_from_cible_insert_only

                conn = sqlite3.connect(DB_PATH)
                try:
                    new_clients_added = sync_new_clients_from_cible_insert_only(
                        conn,
                        id_campagne=_norm_str(id_campagne),
                        id_cible=id_cible,
                        id_action_initiale="2",
                        canal_initial="Appel",
                        action_initial="Appeler",
                    )
                    conn.commit()
                finally:
                    conn.close()

                set_clients_etat_for_campagne(id_campagne, new_etat)

        except Exception:
            new_clients_added = 0

        # si au moins une ligne de cette campagne est en Mail -> traiter mails
        if _campagne_has_mail_action(id_campagne):
            try:
                from app.engine.traitement_mail_engine import run_mail_meta_loop
                # NOTE: la meta-loop traite tous les mails En cours (pas uniquement cette campagne)
                mail_summary = run_mail_meta_loop(max_passes=20, limit_rows_per_pass=9999)
            except Exception as e:
                mail_summary = {"error": "mail_meta_loop_failed", "details": str(e)}

        # route vers queues (métier) après traitement mail
        try:
            output_counts = _route_initial_queues_for_campaign(id_campagne)
        except Exception:
            output_counts = {"crc": 0, "cc": 0, "da": 0, "cc_terrain": 0, "da_terrain": 0}

    return {
        "id_campagne": id_campagne,
        "ok": True,
        "etat": new_etat,
        "deleted_before_refill": deleted,
        "new_clients_added_from_cibles": new_clients_added,
        "mail_meta_loop": mail_summary,
        "output_insert": output_counts,
    }

def sync_new_clients_from_cible_for_campaign(conn: sqlite3.Connection, id_campagne: str) -> Dict[str, Any]:

    """
    Insert-only :
    - Recalcule la cible (via load_clients_df_for_cible + filtres)
    - Ajoute les nouveaux membres dans clients_cibles (+ volume)
    - Ajoute les nouveaux dans clients_campagnes en respectant le modèle (root bloc)
    """
    from app.storage.campagnes_store_sqlite import get_campagne
    from app.storage.clients_cibles_store_sqlite import (
        insert_only_members,
        update_cible_volume_if_column_exists,
    )
    from app.domain.workflow_nav import is_objective_bloc

    c = get_campagne(id_campagne) or {}
    id_cible = _norm_str(c.get("id_cible") or c.get("ID_CIBLE") or c.get("cible_id"))
    id_modele = _norm_str(c.get("id_modele") or c.get("ID_MODELE"))

    if not id_cible or not id_modele:
        return {"ok": False, "error": "campagne missing id_cible or id_modele", "new_cible_members": 0, "new_clients_campagne": 0}

    # 1) Charger modèle -> root bloc (init)
    modele = get_modele_dict(id_modele) or {}
    raw_liste = modele.get("liste_action") or "[]"
    if isinstance(raw_liste, list):
        liste_action = raw_liste
    else:
        try:
            liste_action = json.loads(str(raw_liste))
        except Exception:
            liste_action = []
    if not isinstance(liste_action, list):
        liste_action = []

    root = _find_root_bloc(liste_action) or {}
    id_action_init = _norm_str(root.get("ID")) or "1"
    canal_init = _norm_str(root.get("Canal")) or "Appel"
    action_init = _norm_str(root.get("Action")) or "Appeler"
    if is_objective_bloc(root):
        canal_init = "Objectif"
        action_init = "Objectif"

    current_bloc_init = find_bloc_by_id(liste_action, id_action_init) or root

    # 2) Charger DF cible + filtre rupture relation
    df = load_clients_df_for_cible(id_cible)
    df, _ = _remove_rupture_relation_strict(df)

    radical_col = _detect_radical_col(df)
    radicals = []
    if radical_col:
        for _, r in df.iterrows():
            rc = _norm_str(r.get(radical_col))
            if rc:
                radicals.append(rc)

    # dedup
    radicals = list(dict.fromkeys(radicals))

    # 3) Mettre à jour la cible (insert-only) + volume
    new_cible = insert_only_members(id_cible, radicals)
    update_cible_volume_if_column_exists(id_cible)

    # 4) Ajouter dans clients_campagnes (insert-only, via store)
    #    -> on doit insérer uniquement les RC absents pour cette campagne
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT Radical_compte
            FROM clients_campagnes
            WHERE ID_CAMPAGNE = ?
            """,
            (id_campagne,),
        )
        existing = {_norm_str(x[0]) for x in cur.fetchall() if _norm_str(x[0])}

    finally:
        conn.close()

    to_add = [rc for rc in radicals if _norm_str(rc) and _norm_str(rc) not in existing]

    if not to_add:
        return {"ok": True, "new_cible_members": int(new_cible), "new_clients_campagne": 0}

    today_iso = date.today().isoformat()

    rows = []
    for rc in to_add:
        row_cc = {
            "Nom_campagne": _norm_str(c.get("nom_campagne") or c.get("Nom_campagne")),
            "ID_CAMPAGNE": id_campagne,
            "Radical_compte": rc,
            "Etat_campagne": _norm_str(c.get("etat") or c.get("etat_campagne") or "En cours"),
            "NB_jour_campagne": 0,
            "ID_Action": id_action_init,
            "Canal": canal_init,
            "Action": action_init,
            "Last_action": "",
            "Resultat_last_action": "",
            "Date_last_action": today_iso,
            "NB_jour_last_action": 0,
            "NB_appel": 0,
            "NB_mail": 0,
            "NB_sms": 0,
            "NB_message": 0,
            "NB_approche_commercial": 0,
            "date_debut_campagne": _norm_str(c.get("date_debut") or "")[:10],
            "nb_jour_debut_campagne": 0,
            "conversion": 0,
        }

        # arriv_eche selon ton workflow_nav
        if _norm_str(row_cc.get("Action")) == "Closed":
            row_cc["arriv_eche"] = "Non"
        else:
            row_cc["arriv_eche"] = arrive_echeance(liste_action, current_bloc_init, row_cc)

        rows.append(row_cc)

    inserted = bulk_insert_clients(rows)

    # sécurité : resync Etat_campagne
    set_clients_etat_for_campagne(id_campagne, _norm_str(c.get("etat") or c.get("etat_campagne") or "En cours"))

    return {"ok": True, "new_cible_members": int(new_cible), "new_clients_campagne": int(inserted)}
