from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Tuple
import json
import re
import unicodedata
import time

import pandas as pd

from app.storage.runtime_db import RuntimeConnection, connect_runtime
from app.core.workload_governor import heavy_workload
from app.storage.postgres_db import table_exists, connection as pg_connection
from app.storage.campagnes_store_sqlite import insert_campagne, update_etat
from app.storage.clients_campagnes_store_sqlite import (
    ensure_table as ensure_clients_campagnes_table,
    bulk_insert_clients,
    bulk_insert_clients_from_radical_select,
    set_clients_etat_for_campagne,
)
from app.storage.cibles_store_sqlite import (
    load_clients_df_for_cible,
    build_db_cible_radicals_query,
)
from app.storage.crc_input_store_sqlite import fill_crc_input_from_clients_campagnes
from app.storage.action_vers_cc_store_sqlite import fill_action_vers_cc_from_clients_campagnes
from app.storage.action_vers_da_store_sqlite import fill_action_vers_da_from_clients_campagnes
from app.storage.modele_store_sqlite import get_modele_dict

# NEW: échéance (arriv_eche)
from app.domain.workflow_nav import find_bloc_by_id, arrive_echeance  # retourne dict
from app.domain.terrain_visit_webhook import cancel_visits_for_campaign, dispatch_pending_visits_for_campaign

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

def _get_campaign_state(campagne: Dict[str, Any]) -> str:
    if not isinstance(campagne, dict):
        return ""

    return _norm_str(
        campagne.get("Etat_campagne")
        or campagne.get("etat_campagne")
        or campagne.get("etat")
    )


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


def _validate_campaign_dates(date_debut: str, date_fin: str) -> Tuple[date, date]:
    """
    Valide les dates d'une campagne.

    Règles :
    - date_debut et date_fin sont obligatoires au format ISO YYYY-MM-DD ;
    - date_fin doit être supérieure ou égale à date_debut.
    """
    raw_debut = _norm_str(date_debut)[:10]
    raw_fin = _norm_str(date_fin)[:10]

    if not raw_debut or not raw_fin:
        raise ValueError("date_debut et date_fin sont obligatoires.")

    try:
        d0 = date.fromisoformat(raw_debut)
        d1 = date.fromisoformat(raw_fin)
    except Exception as exc:
        raise ValueError(
            "Format de date invalide. Utiliser YYYY-MM-DD pour date_debut et date_fin."
        ) from exc

    if d1 < d0:
        raise ValueError(
            "Plage de dates invalide : date_fin doit être supérieure ou égale à date_debut."
        )

    return d0, d1


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


def _table_exists(conn: RuntimeConnection, table: str) -> bool:
    return table_exists(str(table or "").strip())


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

    conn = connect_runtime()
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


def _count_radical_select(radical_select, params: List[Any]) -> int:
    """Compte une sélection de radicaux sans la matérialiser côté Python."""
    from psycopg import sql

    query = sql.SQL("SELECT COUNT(*) FROM ({}) AS target_population").format(radical_select)
    with pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or [])
            row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def _route_outputs_for_campaign_bulk(
    id_campagne: str,
    type_campagne: str,
) -> Dict[str, int]:
    """Reconstruit les sorties en bulk sans chevaucher un batch lourd.

    Le slot ne couvre que les écritures PostgreSQL. Les appels réseau terrain
    restent hors du gouverneur afin de ne pas bloquer un batch pendant une I/O.
    """
    counts = {
        "crc": 0,
        "cc": 0,
        "da": 0,
        "cc_terrain": 0,
        "da_terrain": 0,
    }

    with heavy_workload("interactive"):
        _delete_outputs_for_campagne(id_campagne)
        counts["crc"] = int(
            fill_crc_input_from_clients_campagnes(id_campagne) or 0
        )

        if _norm_str(type_campagne) != "avec_action_terrain":
            counts["da"] = int(
                fill_action_vers_da_from_clients_campagnes(id_campagne) or 0
            )
            counts["cc"] = int(
                fill_action_vers_cc_from_clients_campagnes(id_campagne) or 0
            )

    if _norm_str(type_campagne) == "avec_action_terrain":
        dispatch = dispatch_pending_visits_for_campaign(id_campagne)
        counts["external_visit_queued"] = int(dispatch.get("queued") or 0)
        counts["external_visit_pending"] = int(dispatch.get("pending") or 0)
        counts["external_visit_sent"] = int(dispatch.get("sent") or 0)
        counts["external_visit_skipped"] = int(dispatch.get("skipped") or 0)
        counts["external_visit_errors"] = int(dispatch.get("errors") or 0)

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
    visitMode: str | None = None,
    visitPurpose: str | None = None,
) -> Dict[str, Any]:
    """
    Crée campagne + peuple clients_campagnes.

    Règles appliquées à la création :
    - Exclure STATUT_CLIENT == 'Rupture de relation'
    - Si la campagne démarre "En cours":
        - si la première action est Mail => exécuter mail meta-loop immédiatement
        - puis router initialement vers CRC/CC/DA via route_after_update (métier)
    """

    started_at = time.perf_counter()
    target_ready_at = started_at
    clients_inserted_at = started_at

    # 0) Validation des dates + état campagne
    _validate_campaign_dates(date_debut, date_fin)

    if not etat_campagne:
        etat_campagne = _infer_etat(date_debut, date_fin)
    
    type_campagne = _norm_str(type_campagne) or "sans_action_terrain"
    if type_campagne not in ("sans_action_terrain", "avec_action_terrain"):
        raise ValueError("type_campagne invalide: sans_action_terrain | avec_action_terrain")

    visitMode = _norm_str(visitMode) or None
    visitPurpose = _norm_str(visitPurpose) or None

    if type_campagne == "avec_action_terrain":
        if visitMode not in ("A_DISTANCE", "TERRAIN"):
            raise ValueError("visitMode invalide: A_DISTANCE | TERRAIN")
        if visitPurpose not in ("COMMERCIAL", "RECOUVREMENT"):
            raise ValueError("visitPurpose invalide: COMMERCIAL | RECOUVREMENT")
    else:
        visitMode = None
        visitPurpose = None

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

    # 3) Population cible
    # Pour une cible DB, PostgreSQL reste la source de vérité de bout en bout:
    # aucun DataFrame de centaines de milliers de lignes n'est matérialisé.
    db_select_all = build_db_cible_radicals_query(
        id_cible,
        exclude_rupture_relation=False,
    )
    db_select_filtered = build_db_cible_radicals_query(
        id_cible,
        exclude_rupture_relation=True,
    )

    df = None
    if db_select_all is not None and db_select_filtered is not None:
        raw_query, raw_params = db_select_all
        filtered_query, filtered_params = db_select_filtered
        with heavy_workload("interactive"):
            nb_init = _count_radical_select(raw_query, raw_params)
            nb_apres = _count_radical_select(filtered_query, filtered_params)
        removed_rupture = max(0, nb_init - nb_apres)
    else:
        # Fallback inchangé pour les cibles fichier plat.
        df = load_clients_df_for_cible(id_cible)
        nb_init = int(len(df))
        df, removed_rupture = _remove_rupture_relation_strict(df)
        nb_apres = int(len(df))
        filtered_query = None
        filtered_params = []

    target_ready_at = time.perf_counter()

    # 4) Création campagne
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
        visitMode=visitMode,
        visitPurpose=visitPurpose,
    )

    # 5) Valeurs initiales communes à tous les clients de la campagne.
    today_iso = date.today().isoformat()
    row_template = {
        "Nom_campagne": nom_campagne,
        "ID_CAMPAGNE": id_campagne,
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
        "NB_da": 0,
        "NB_cc": 0,
        "NB_push": 0,
        "date_debut_campagne": _norm_str(date_debut)[:10],
        "nb_jour_debut_campagne": 0,
        "conversion": 0,
    }

    # arriv_eche ne dépend ici que du bloc initial et de
    # NB_jour_last_action=0: il est donc identique pour toute la population.
    if _norm_str(etat_campagne) != "En cours":
        row_template["arriv_eche"] = "Non"
    else:
        row_template["arriv_eche"] = arrive_echeance(
            liste_action,
            current_bloc_init,
            row_template,
        )

    # 6) Affectation massive
    if filtered_query is not None:
        with heavy_workload("interactive"):
            inserted_clients = bulk_insert_clients_from_radical_select(
                filtered_query,
                filtered_params,
                row_template,
                only_new=False,
            )
    else:
        radical_col = _detect_radical_col(df) if df is not None else ""
        rows: List[Dict[str, Any]] = []
        if df is not None and radical_col:
            for _, r in df.iterrows():
                rc = _norm_str(r.get(radical_col))
                if not rc:
                    continue
                row_cc = dict(row_template)
                row_cc["Radical_compte"] = rc
                rows.append(row_cc)
        inserted_clients = bulk_insert_clients(rows)

    clients_inserted_at = time.perf_counter()

    # Les lignes viennent d'être insérées avec le bon état : pas de second
    # UPDATE massif inutile ici.
    output_counts = {"crc": 0, "cc": 0, "da": 0, "cc_terrain": 0, "da_terrain": 0}
    mail_summary = None

    # 8) Si En cours: traitement Mail éventuel puis reconstruction bulk des outputs.
    if etat_campagne == "En cours":
        if _is_first_action_mail(canal_init, action_init):
            try:
                from app.engine.traitement_mail_engine import run_mail_meta_loop
                mail_summary = run_mail_meta_loop(max_passes=20, limit_rows_per_pass=500, id_campagne=id_campagne)
            except Exception as e:
                mail_summary = {"error": "mail_meta_loop_failed", "details": str(e)}

        try:
            output_counts = _route_outputs_for_campaign_bulk(
                id_campagne,
                type_campagne,
            )
        except Exception as e:
            output_counts = {
                "crc": 0,
                "cc": 0,
                "da": 0,
                "cc_terrain": 0,
                "da_terrain": 0,
                "external_visit_sent": 0,
                "external_visit_skipped": 0,
                "external_visit_errors": 0,
                "error": str(e),
            }

    finished_at = time.perf_counter()

    return {
        "id_campagne": id_campagne,
        "nb_cible_initial": nb_init,
        "nb_apres_filtrage": nb_apres,
        "nb_exclus_rupture": int(removed_rupture),
        "nb_clients_insérés": int(inserted_clients),
        "etat_campagne": etat_campagne,
        "type_campagne": type_campagne,
        "id_action_initial": id_action_init,
        "canal_initial": canal_init,
        "action_initiale": action_init,
        "mail_meta_loop": mail_summary,
        "output_insert": output_counts,
        "bulk_mode": "postgresql_native" if filtered_query is not None else "file_fallback",
        "timings_ms": {
            "target": int((target_ready_at - started_at) * 1000),
            "insert_clients_campagnes": int((clients_inserted_at - target_ready_at) * 1000),
            "routing_outputs": int((finished_at - clients_inserted_at) * 1000),
            "total": int((finished_at - started_at) * 1000),
        },
        "visitMode": visitMode,
        "visitPurpose": visitPurpose,
    }


def annuler_campagne(id_campagne: str) -> Dict[str, Any]:
    """
    Annule une campagne:
    - supprime côté plateforme d'animation commerciale les tiers déjà affectés
    - campagne.etat = 'Annulée'
    - clients_campagnes.Etat_campagne = 'Annulée'
    - supprime les queues internes liées à la campagne
    """
    external_cancel = {"ok": True, "skipped": True, "reason": "not_called"}

    try:
        external_cancel = cancel_visits_for_campaign(
            id_campagne,
            local_status="cancelled_on_campaign_cancel",
        )
    except Exception as e:
        external_cancel = {"ok": False, "error": str(e)}

    if not external_cancel.get("ok", False) and not external_cancel.get("skipped", False):
        return {
            "id_campagne": id_campagne,
            "ok": False,
            "error": "external_visit_cancel_failed",
            "external_cancel": external_cancel,
            "deleted": {
                "crc": 0,
                "cc": 0,
                "da": 0,
                "cc_terrain": 0,
                "da_terrain": 0,
            },
        }

    update_etat(id_campagne, "Annulée")
    set_clients_etat_for_campagne(id_campagne, "Annulée")

    deleted = {
        "crc": 0,
        "cc": 0,
        "da": 0,
        "cc_terrain": 0,
        "da_terrain": 0,
    }

    try:
        deleted = _delete_outputs_for_campagne(id_campagne)
    except Exception as e:
        return {
            "id_campagne": id_campagne,
            "ok": False,
            "error": str(e),
            "external_cancel": external_cancel,
            "deleted": deleted,
        }

    return {
        "id_campagne": id_campagne,
        "ok": True,
        "etat": "Annulée",
        "external_cancel": external_cancel,
        "deleted": deleted,
    }


def _campagne_has_mail_action(id_campagne: str) -> bool:
    """
    True si au moins un client de la campagne a un bloc courant Mail (action Message/Mail).
    On ne vérifie pas l'envoi, seulement la présence d'un besoin.
    """
    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1
            FROM clients_campagnes
            WHERE ID_CAMPAGNE = ?
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
    - supprime côté plateforme d'animation commerciale les tiers déjà affectés
    - campagne.etat = 'En pause'
    - clients_campagnes.Etat_campagne = 'En pause'
    - supprime les queues internes liées

    Point clé:
    les logs external_visit_dispatches status='sent' sont libérés après DELETE
    externe réussi pour permettre un renvoi lors de la réactivation.
    """
    from app.storage.campagnes_store_sqlite import get_campagne

    campagne = get_campagne(id_campagne) or {}

    if not campagne:
        return {
            "id_campagne": id_campagne,
            "ok": False,
            "error": "Campagne introuvable.",
        }

    etat_actuel = _get_campaign_state(campagne)

    if etat_actuel == "Terminée":
        return {
            "id_campagne": id_campagne,
            "ok": False,
            "error": "Une campagne terminée ne peut pas être mise en pause.",
            "etat": etat_actuel,
        }

    external_cancel = {"ok": True, "skipped": True, "reason": "not_called"}

    try:
        external_cancel = cancel_visits_for_campaign(
            id_campagne,
            local_status="cancelled_on_campaign_pause",
        )
    except Exception as e:
        external_cancel = {"ok": False, "error": str(e)}

    if not external_cancel.get("ok", False) and not external_cancel.get("skipped", False):
        return {
            "id_campagne": id_campagne,
            "ok": False,
            "error": "external_visit_cancel_failed",
            "external_cancel": external_cancel,
            "deleted": {
                "crc": 0,
                "cc": 0,
                "da": 0,
                "cc_terrain": 0,
                "da_terrain": 0,
            },
        }

    update_etat(id_campagne, "En pause")
    set_clients_etat_for_campagne(id_campagne, "En pause")

    deleted = {
        "crc": 0,
        "cc": 0,
        "da": 0,
        "cc_terrain": 0,
        "da_terrain": 0,
    }

    try:
        deleted = _delete_outputs_for_campagne(id_campagne)
    except Exception as e:
        return {
            "id_campagne": id_campagne,
            "ok": False,
            "error": str(e),
            "external_cancel": external_cancel,
            "deleted": deleted,
        }

    return {
        "id_campagne": id_campagne,
        "ok": True,
        "etat": "En pause",
        "external_cancel": external_cancel,
        "deleted": deleted,
    }

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

    if new_etat == "En cours":
        conn = connect_runtime()

        try:
            cur = conn.cursor()

            cur.execute(
                """
                UPDATE clients_campagnes
                SET Date_last_action =
                    (
                        CURRENT_DATE
                        - COALESCE(NB_jour_last_action, 0)
                    )::text
                WHERE ID_CAMPAGNE = ?
                """,
                (
                    id_campagne,
                ),
            )

            conn.commit()

        finally:
            conn.close()    

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
            conn = connect_runtime()
            try:
                sync_result = sync_new_clients_from_cible_for_campaign(
                    conn,
                    id_campagne,
                )

                if sync_result.get("ok"):
                    new_clients_added = int(
                        sync_result.get("new_clients_campagne") or 0
                    )
                    conn.commit()
                else:
                    new_clients_added = 0
                    conn.rollback()

            finally:
                conn.close()

            set_clients_etat_for_campagne(
                id_campagne,
                new_etat,
            )

        except Exception:
            new_clients_added = 0

        # si au moins une ligne de cette campagne est en Mail -> traiter mails
        if _campagne_has_mail_action(id_campagne):
            try:
                from app.engine.traitement_mail_engine import run_mail_meta_loop
                mail_summary = run_mail_meta_loop(max_passes=20, limit_rows_per_pass=500, id_campagne=id_campagne)
            except Exception as e:
                mail_summary = {"error": "mail_meta_loop_failed", "details": str(e)}

        # Reconstruction bulk des queues après traitement mail.
        type_campagne = _norm_str(c.get("type_campagne")) or "sans_action_terrain"
        try:
            output_counts = _route_outputs_for_campaign_bulk(
                id_campagne,
                type_campagne,
            )
        except Exception as e:
            output_counts = {
                "crc": 0,
                "cc": 0,
                "da": 0,
                "cc_terrain": 0,
                "da_terrain": 0,
                "error": str(e),
            }

        if type_campagne == "avec_action_terrain":
            external_dispatch_after_activation = {
                "ok": int(output_counts.get("external_visit_errors") or 0) == 0,
                "sent": int(output_counts.get("external_visit_sent") or 0),
                "skipped": int(output_counts.get("external_visit_skipped") or 0),
                "errors": int(output_counts.get("external_visit_errors") or 0),
            }
        else:
            external_dispatch_after_activation = {
                "ok": True,
                "skipped": True,
                "reason": "sans_action_terrain",
            }

    else:
        external_dispatch_after_activation = {
            "ok": True,
            "skipped": True,
            "reason": f"etat_{new_etat}",
        }

    return {
        "id_campagne": id_campagne,
        "ok": True,
        "etat": new_etat,
        "deleted_before_refill": deleted,
        "new_clients_added_from_cibles": new_clients_added,
        "mail_meta_loop": mail_summary,
        "output_insert": output_counts,
        "external_dispatch_after_activation": external_dispatch_after_activation,
    }

def sync_new_clients_from_cible_for_campaign(conn: RuntimeConnection, id_campagne: str) -> Dict[str, Any]:
    """
    Synchronisation insert-only de la cible vers la campagne.

    Les cibles DB utilisent INSERT ... SELECT directement dans PostgreSQL.
    Les cibles fichier plat conservent le chemin historique DataFrame.
    """
    from app.storage.campagnes_store_sqlite import get_campagne
    from app.storage.clients_cibles_store_sqlite import (
        insert_only_members,
        insert_only_members_from_radical_select,
        update_cible_volume_if_column_exists,
    )
    from app.domain.workflow_nav import is_objective_bloc

    _ = conn  # conservé dans la signature pour compatibilité avec le batch

    c = get_campagne(id_campagne) or {}
    id_cible = _norm_str(c.get("id_cible") or c.get("ID_CIBLE") or c.get("cible_id"))
    id_modele = _norm_str(c.get("id_modele") or c.get("ID_MODELE"))

    if not id_cible or not id_modele:
        return {"ok": False, "error": "campagne missing id_cible or id_modele", "new_cible_members": 0, "new_clients_campagne": 0}

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
    campagne_state = _get_campaign_state(c) or "En cours"

    row_template = {
        "Nom_campagne": _norm_str(c.get("nom_campagne") or c.get("Nom_campagne")),
        "ID_CAMPAGNE": id_campagne,
        "Etat_campagne": campagne_state,
        "NB_jour_campagne": 0,
        "ID_Action": id_action_init,
        "Canal": canal_init,
        "Action": action_init,
        "Last_action": "",
        "Resultat_last_action": "",
        "Date_last_action": date.today().isoformat(),
        "NB_jour_last_action": 0,
        "NB_appel": 0,
        "NB_mail": 0,
        "NB_sms": 0,
        "NB_message": 0,
        "NB_approche_commercial": 0,
        "NB_da": 0,
        "NB_cc": 0,
        "NB_push": 0,
        "date_debut_campagne": _norm_str(c.get("date_debut") or "")[:10],
        "nb_jour_debut_campagne": 0,
        "conversion": 0,
    }
    row_template["arriv_eche"] = (
        arrive_echeance(liste_action, current_bloc_init, row_template)
        if campagne_state == "En cours"
        else "Non"
    )

    db_select = build_db_cible_radicals_query(
        id_cible,
        exclude_rupture_relation=True,
    )

    if db_select is not None:
        radical_query, radical_params = db_select
        new_cible = insert_only_members_from_radical_select(
            id_cible,
            radical_query,
            radical_params,
        )
        inserted = bulk_insert_clients_from_radical_select(
            radical_query,
            radical_params,
            row_template,
            only_new=True,
        )
        update_cible_volume_if_column_exists(id_cible)
        return {
            "ok": True,
            "new_cible_members": int(new_cible),
            "new_clients_campagne": int(inserted),
        }

    # Fallback fichier plat.
    df = load_clients_df_for_cible(id_cible)
    df, _ = _remove_rupture_relation_strict(df)
    radical_col = _detect_radical_col(df)
    radicals = []
    if radical_col:
        radicals = list(dict.fromkeys(
            _norm_str(r.get(radical_col))
            for _, r in df.iterrows()
            if _norm_str(r.get(radical_col))
        ))

    new_cible = insert_only_members(id_cible, radicals)
    update_cible_volume_if_column_exists(id_cible)

    # Pour les fichiers plats on conserve un contrôle Python des existants.
    runtime_conn = connect_runtime()
    try:
        cur = runtime_conn.cursor()
        cur.execute("SELECT Radical_compte FROM clients_campagnes WHERE ID_CAMPAGNE = ?", (id_campagne,))
        existing = {_norm_str(row[0]) for row in cur.fetchall() if _norm_str(row[0])}
    finally:
        runtime_conn.close()

    rows = []
    for rc in radicals:
        if rc in existing:
            continue
        row_cc = dict(row_template)
        row_cc["Radical_compte"] = rc
        rows.append(row_cc)

    inserted = bulk_insert_clients(rows)
    return {
        "ok": True,
        "new_cible_members": int(new_cible),
        "new_clients_campagne": int(inserted),
    }
