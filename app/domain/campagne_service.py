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
from app.storage.modele_store_sqlite import get_modele_by_id

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


def _filter_objectif_deja_atteint(df: pd.DataFrame, variable_cible: str, objectif: str) -> Tuple[pd.DataFrame, int]:
    """
    A la création de campagne, ne pas rajouter les lignes qui ont déjà atteint l'objectif.

    Compat:
    - objectif "simple" (legacy): exclure df[variable_cible] == objectif (normalisé)
    - objectif "multi" JSON: {"op":"AND|OR","items":[{...},...]} => exclure si l'expression est déjà vraie
    """
    obj_raw = _norm_str(objectif).strip()
    if not obj_raw:
        return df, 0

    # --- helper: try parse JSON objectif
    expr = None
    if obj_raw.startswith("{") or obj_raw.startswith("["):
        try:
            expr = json.loads(obj_raw)
        except Exception:
            expr = None

    # =========================
    # ✅ Multi-objectif JSON
    # =========================
    if isinstance(expr, dict) and "op" in expr and "items" in expr:
        op = _norm_str(expr.get("op")).upper()
        items = expr.get("items")

        if op not in ("AND", "OR") or not isinstance(items, list) or len(items) == 0:
            return df, 0

        masks: List[pd.Series] = []

        for it in items:
            if not isinstance(it, dict):
                continue

            var = _norm_str(it.get("variable"))
            typ = _norm_str(it.get("type")).lower()

            if not var or var not in df.columns:
                # si variable absente => item non évaluable => AND => bloque, OR => ignore
                if op == "AND":
                    masks.append(pd.Series([False] * len(df), index=df.index))
                continue

            # item catégoriel
            if typ == "cat":
                val = _norm_str(it.get("value"))
                if not val:
                    if op == "AND":
                        masks.append(pd.Series([False] * len(df), index=df.index))
                    continue
                s = df[var].apply(_norm_cmp)
                masks.append(s.eq(_norm_cmp(val)))
                continue

            # item numérique
            if typ == "num":
                mn = it.get("min", None)
                mx = it.get("max", None)
                s_num = pd.to_numeric(df[var], errors="coerce")

                m = pd.Series([True] * len(df), index=df.index)
                if mn is not None and str(mn).strip() != "":
                    try:
                        m = m & (s_num >= float(mn))
                    except Exception:
                        m = m & False
                if mx is not None and str(mx).strip() != "":
                    try:
                        m = m & (s_num <= float(mx))
                    except Exception:
                        m = m & False

                masks.append(m.fillna(False))
                continue

            # type inconnu
            if op == "AND":
                masks.append(pd.Series([False] * len(df), index=df.index))

        if not masks:
            return df, 0

        if op == "AND":
            final_mask = masks[0]
            for m in masks[1:]:
                final_mask = final_mask & m
        else:  # OR
            final_mask = masks[0]
            for m in masks[1:]:
                final_mask = final_mask | m

        removed = int(final_mask.sum())
        return df.loc[~final_mask].copy(), removed

    # =========================
    # ✅ Legacy (objectif simple)
    # =========================
    var = _norm_str(variable_cible)
    obj = _norm_str(objectif)
    if not var or not obj:
        return df, 0
    if var not in df.columns:
        return df, 0

    s = df[var].apply(_norm_cmp)
    mask = s.eq(_norm_cmp(obj))
    removed = int(mask.sum())
    return df.loc[~mask].copy(), removed



def _safe_json_loads(s: str, default):
    try:
        return json.loads(s)
    except Exception:
        return default


def _find_root_bloc(liste_action: list) -> dict | None:
    if not isinstance(liste_action, list):
        return None
    for b in liste_action:
        if isinstance(b, dict) and _norm_str(b.get("Bloc_mere")).lower() == "oui":
            return b
    for b in liste_action:
        if isinstance(b, dict) and _norm_str(b.get("ID")) == "1":
            return b
    return liste_action[0] if liste_action else None


def _fill_outputs_for_campaign(id_campagne: str) -> Dict[str, int]:
    """
    Remplit les tables output (crc_input / action_vers_cc / action_vers_da).
    """
    from app.storage.crc_input_store_sqlite import fill_crc_input_from_clients_campagnes
    from app.storage.action_vers_cc_store_sqlite import fill_action_vers_cc_from_clients_campagnes
    from app.storage.action_vers_da_store_sqlite import fill_action_vers_da_from_clients_campagnes

    n_crc = fill_crc_input_from_clients_campagnes(id_campagne)
    n_cc = fill_action_vers_cc_from_clients_campagnes(id_campagne)
    n_da = fill_action_vers_da_from_clients_campagnes(id_campagne)

    return {"crc": int(n_crc), "cc": int(n_cc), "da": int(n_da)}


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
    # noms attendus (d'après tes stores)
    tables = {
        "crc": "crc_input",
        "cc": "vers_cc",
        "da": "vers_da",
    }

    deleted = {"crc": 0, "cc": 0, "da": 0}

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


# =========================================================
def create_campagne(
    nom_campagne: str,
    id_modele: str,
    id_cible: str,
    date_debut: str,
    date_fin: str,
    etat_campagne: str | None = None,
    description: str | None = None,
) -> Dict[str, Any]:
    """
    Crée campagne + peuple clients_campagnes.

    Règles appliquées à la création :
    - Exclure STATUT_CLIENT == 'Rupture de relation'
    - Exclure les clients ayant déjà atteint l'objectif (variable_cible / objectif)
    - Si la campagne démarre "En cours":
        - si la première action est Mail => exécuter mail meta-loop immédiatement
        - puis remplir les outputs CRC/CC/DA (état post-mail)
    """

    # 0) Etat campagne
    if not etat_campagne:
        etat_campagne = _infer_etat(date_debut, date_fin)

    # 1) Charger modèle
    modele = get_modele_by_id(id_modele)
    if not modele:
        raise ValueError(f"Modèle introuvable: {id_modele}")

    # 2) Root bloc (ID_Action/Canal/Action init)
    liste_action = _safe_json_loads(modele.get("liste_action") or "[]", [])
    root = _find_root_bloc(liste_action) or {}

    id_action_init = _norm_str(root.get("ID")) or "1"
    canal_init = _norm_str(root.get("Canal")) or "Appel"
    action_init = _norm_str(root.get("Action")) or "Contacter"

    # Bloc courant initial (pour calcul arriv_eche)
    current_bloc_init = find_bloc_by_id(liste_action, id_action_init) or root

    # 3) Charger population cible
    df = load_clients_df_for_cible(id_cible)
    nb_init = int(len(df))

    # 4) Filtre rupture relation
    df, removed_rupture = _remove_rupture_relation_strict(df)

    # 5) Filtre objectif déjà atteint
    variable_cible = _norm_str(modele.get("variable_cible"))
    objectif = _norm_str(modele.get("objectif"))
    df, removed_obj = _filter_objectif_deja_atteint(df, variable_cible, objectif)

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
    )

    # 7) Préparer lignes clients_campagnes
    radical_col = _detect_radical_col(df)
    statut_col = _detect_statut_col(df)

    rows: List[Dict[str, Any]] = []
    today_iso = date.today().isoformat()

    for _, r in df.iterrows():
        rc = _norm_str(r.get(radical_col))
        if not rc:
            continue

        statut_avant = _norm_str(r.get(statut_col)) if statut_col else ""

        row_cc = {
            "Nom_campagne": nom_campagne,
            "ID_CAMPAGNE": id_campagne,
            "Radical_compte": rc,
            "statut_avant_campagne": statut_avant,
            "statut_actuel": statut_avant,
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
            "date_debut_campagne": _norm_str(date_debut)[:10],  # début "logique" de la campagne
            "nb_jour_debut_campagne": 0,
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

    output_counts = {"crc": 0, "cc": 0, "da": 0}
    mail_summary = None

    # 10) Si "En cours":
    if etat_campagne == "En cours":
        # (A) Si 1ère action = Mail => traiter immédiatement
        if _is_first_action_mail(canal_init, action_init):
            try:
                # nouveau mail engine (méta boucle)
                from app.engine.traitement_mail_engine import run_mail_meta_loop

                mail_summary = run_mail_meta_loop(max_passes=20, limit_rows_per_pass=9999)
            except Exception as e:
                mail_summary = {"error": "mail_meta_loop_failed", "details": str(e)}

        # (B) Remplir outputs APRÈS le traitement mail (état post-mail)
        try:
            output_counts = _fill_outputs_for_campaign(id_campagne)
        except Exception:
            output_counts = {"crc": 0, "cc": 0, "da": 0}

    return {
        "id_campagne": id_campagne,
        "nb_cible_initial": nb_init,
        "nb_apres_filtrage": nb_apres,
        "nb_exclus_rupture": int(removed_rupture),
        "nb_exclus_objectif_atteint": int(removed_obj),
        "nb_clients_insérés": int(len(rows)),
        "etat_campagne": etat_campagne,
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
    - action_vers_cc
    - action_vers_da
    """
    update_etat(id_campagne, "Annulée")
    set_clients_etat_for_campagne(id_campagne, "Annulée")

    deleted = {"crc": 0, "cc": 0, "da": 0}
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

    deleted = {"crc": 0, "cc": 0, "da": 0}
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
        - remplit à nouveau les queues (crc_input / vers_cc / vers_da)
    - si Planifiée ou Terminée:
        - supprime les queues de cette campagne (sécurité)
        - ne remplit rien
    """
    # lecture campagne
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

    # toujours nettoyer queues associées avant décision
    deleted = {"crc": 0, "cc": 0, "da": 0}
    try:
        deleted = _delete_outputs_for_campagne(id_campagne)
    except Exception:
        pass

    mail_summary = None
    output_counts = {"crc": 0, "cc": 0, "da": 0}
    new_clients_added = 0  # NEW

    if new_etat == "En cours":
        # NEW: sync nouveaux clients depuis la cible (INSERT ONLY) avant mail/rebuild
        try:
            id_cible = _norm_str(c.get("id_cible") or c.get("ID_CIBLE") or c.get("cible_id"))
            if id_cible:
                # la fonction est dans batch_manuel (tu l'as ajoutée là-bas)
                from app.scripts.batch_manuel import sync_new_clients_from_cible_insert_only

                # ouverture connexion DB (on essaie _connect si présent, sinon sqlite3/DB_PATH)
                conn = None
                try:
                    try:
                        conn = _connect()  # si ton module a déjà ce helper
                    except Exception:
                        import sqlite3
                        conn = sqlite3.connect(DB_PATH)  # si DB_PATH existe dans ce module

                    new_clients_added = sync_new_clients_from_cible_insert_only(
                        conn,
                        id_campagne=_norm_str(id_campagne),
                        id_cible=id_cible,
                        # ⚠️ valeurs initiales comme dans ton batch (tu peux les rendre dynamiques ensuite)
                        id_action_initiale="2",
                        canal_initial="Appel",
                        action_initial="Appeler",
                    )
                    conn.commit()
                finally:
                    try:
                        if conn is not None:
                            conn.close()
                    except Exception:
                        pass

                # Important: aligner l'état des nouveaux entrants aussi
                set_clients_etat_for_campagne(id_campagne, new_etat)

        except Exception:
            # On ne bloque pas l'activation si le sync échoue
            new_clients_added = 0

        # si au moins une ligne de cette campagne est en Mail -> traiter mails
        if _campagne_has_mail_action(id_campagne):
            try:
                from app.engine.traitement_mail_engine import run_mail_meta_loop
                # NOTE: la meta-loop traite tous les mails En cours (pas uniquement cette campagne)
                mail_summary = run_mail_meta_loop(max_passes=20, limit_rows_per_pass=9999)
            except Exception as e:
                mail_summary = {"error": "mail_meta_loop_failed", "details": str(e)}

        # remplir queues (après traitement mail)
        try:
            output_counts = _fill_outputs_for_campaign(id_campagne)
        except Exception:
            output_counts = {"crc": 0, "cc": 0, "da": 0}

    return {
        "id_campagne": id_campagne,
        "ok": True,
        "etat": new_etat,
        "deleted_before_refill": deleted,
        "new_clients_added_from_cibles": new_clients_added,  # NEW
        "mail_meta_loop": mail_summary,
        "output_insert": output_counts,
    }
