from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Tuple, Sequence
import json
import re
import unicodedata
import time


from app.storage.runtime_db import RuntimeConnection, connect_runtime
from app.core.workload_governor import heavy_workload
from app.storage.postgres_db import table_exists, connection as pg_connection
from app.storage.campagnes_store_sqlite import (
    insert_campagne,
    update_etat,
    get_campagne,
    set_execution_status,
)
from app.storage.clients_campagnes_store_sqlite import (
    ensure_table as ensure_clients_campagnes_table,
    bulk_insert_clients_from_radical_select,
)
from app.storage.cibles_store_sqlite import (
    build_db_cible_radicals_query,
    get_cible,
)
from app.storage.crc_input_store_sqlite import fill_crc_input_from_clients_campagnes
from app.storage.action_vers_cc_store_sqlite import fill_action_vers_cc_from_clients_campagnes
from app.storage.action_vers_da_store_sqlite import fill_action_vers_da_from_clients_campagnes
from app.storage.modele_store_sqlite import get_modele_dict

# NEW: échéance (arriv_eche)
from app.domain.workflow_nav import find_bloc_by_id, arrive_echeance  # retourne dict
from app.domain.send_time import normalize_creneau
from app.domain.terrain_visit_webhook import cancel_visits_for_campaign, dispatch_pending_visits_for_campaign

# =========================================================
# Helpers
# =========================================================
def _norm_str(x: Any) -> str:
    if x is None:
        return ""
    value = str(x).strip()
    return "" if value.lower() in {"none", "nan", "nat"} else value

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

    return counts


# =========================================================
def _validate_campaign_creation_request(
    *,
    id_modele: str,
    id_cible: str,
    date_debut: str,
    date_fin: str,
    etat_campagne: str | None,
    type_campagne: str | None,
    visitMode: str | None,
    visitPurpose: str | None,
) -> Dict[str, Any]:
    """Validation légère exécutée dans la requête HTTP avant mise en file."""
    _validate_campaign_dates(date_debut, date_fin)
    state = _norm_str(etat_campagne) or _infer_etat(date_debut, date_fin)
    campaign_type = _norm_str(type_campagne) or "sans_action_terrain"
    if campaign_type not in ("sans_action_terrain", "avec_action_terrain"):
        raise ValueError("type_campagne invalide: sans_action_terrain | avec_action_terrain")

    visit_mode = _norm_str(visitMode) or None
    visit_purpose = _norm_str(visitPurpose) or None
    if campaign_type == "avec_action_terrain":
        if visit_mode not in ("A_DISTANCE", "TERRAIN"):
            raise ValueError("visitMode invalide: A_DISTANCE | TERRAIN")
        if visit_purpose not in ("COMMERCIAL", "RECOUVREMENT"):
            raise ValueError("visitPurpose invalide: COMMERCIAL | RECOUVREMENT")
    else:
        visit_mode = None
        visit_purpose = None

    if not (get_modele_dict(id_modele) or {}):
        raise ValueError(f"Modèle introuvable: {id_modele}")

    cible_meta = get_cible(id_cible) or {}
    if not cible_meta:
        raise ValueError(f"Cible introuvable: {id_cible}")

    # La source est une configuration d'infrastructure, jamais un choix métier.
    # Dans l'instance actuelle, `clients` est le datamart canonique.
    data_source_code = _norm_str(cible_meta.get("data_source_code")) or "internal"
    if data_source_code != "internal":
        raise RuntimeError(
            "La source client configurée pour cette instance nécessite son adaptateur "
            "d'orchestration de déploiement. Aucune population externe ne sera copiée localement."
        )

    return {
        "etat_campagne": state,
        "type_campagne": campaign_type,
        "visitMode": visit_mode,
        "visitPurpose": visit_purpose,
    }


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
    """Crée immédiatement la campagne puis délègue son peuplement à un job persistant.

    UX: la requête HTTP ne dépend plus du volume de la cible. Le travail massif est
    repris par l'orchestrateur, avec priorité sur les batchs de maintenance.
    """
    started_at = time.perf_counter()
    normalized = _validate_campaign_creation_request(
        id_modele=id_modele,
        id_cible=id_cible,
        date_debut=date_debut,
        date_fin=date_fin,
        etat_campagne=etat_campagne,
        type_campagne=type_campagne,
        visitMode=visitMode,
        visitPurpose=visitPurpose,
    )

    # L'insertion de la campagne ET du job est atomique dans la même transaction.
    id_campagne = insert_campagne(
        nom_campagne=nom_campagne,
        id_modele=id_modele,
        id_cible=id_cible,
        date_debut=date_debut,
        date_fin=date_fin,
        etat_campagne=normalized["etat_campagne"],
        description=description,
        type_campagne=normalized["type_campagne"],
        visitMode=normalized["visitMode"],
        visitPurpose=normalized["visitPurpose"],
        execution_status="preparing",
        enqueue_prepare_job=True,
    )

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    return {
        "id_campagne": id_campagne,
        "nb_cible_initial": 0,
        "nb_apres_filtrage": 0,
        "nb_exclus_rupture": 0,
        "nb_clients_insérés": 0,
        "etat_campagne": normalized["etat_campagne"],
        "type_campagne": normalized["type_campagne"],
        "visitMode": normalized["visitMode"],
        "visitPurpose": normalized["visitPurpose"],
        "execution_status": "preparing",
        "async": True,
        "bulk_mode": "postgresql_native_async",
        "timings_ms": {"enqueue": elapsed_ms, "total": elapsed_ms},
    }


def prepare_campagne_execution(
    id_campagne: str,
    *,
    progress=None,
    cancel_check=None,
) -> Dict[str, Any]:
    """Prépare une campagne dans un worker sans matérialiser sa population en Python."""
    started_at = time.perf_counter()

    def _progress(step: int, message: str) -> None:
        if callable(progress):
            progress(step, message)

    def _cancelled() -> bool:
        return bool(callable(cancel_check) and cancel_check())

    campagne = get_campagne(id_campagne) or {}
    if not campagne:
        raise ValueError(f"Campagne introuvable: {id_campagne}")
    if _get_campaign_state(campagne) == "Annulée" or _cancelled():
        raise RuntimeError("job_cancelled")

    set_execution_status(id_campagne, "processing", error=None, started=True)

    # 1) Modèle et bloc initial.
    modele = get_modele_dict(_norm_str(campagne.get("id_modele"))) or {}
    if not modele:
        raise ValueError(f"Modèle introuvable: {campagne.get('id_modele')}")
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
    creneau_init = normalize_creneau(root.get("Creneau"))
    from app.domain.workflow_nav import is_objective_bloc
    if is_objective_bloc(root):
        canal_init = "Objectif"
        action_init = "Objectif"
        creneau_init = "Indifferent"
    current_bloc_init = find_bloc_by_id(liste_action, id_action_init) or root

    # 2) Requête de cible : le volume reste dans PostgreSQL.
    # Le watermark est capturé AVANT le premier SELECT massif. Tout changement
    # concurrent recevra un seq supérieur et sera repris incrémentalement.
    from app.targeting.store import current_change_seq, initialize_campaign_state

    id_cible = _norm_str(campagne.get("id_cible"))
    target_sync_start_seq = current_change_seq()
    db_select_all = build_db_cible_radicals_query(id_cible, exclude_rupture_relation=False)
    db_select_filtered = build_db_cible_radicals_query(id_cible, exclude_rupture_relation=True)
    if db_select_all is None or db_select_filtered is None:
        raise RuntimeError("Aucun chemin SQL-native disponible pour cette cible.")

    raw_query, raw_params = db_select_all
    filtered_query, filtered_params = db_select_filtered
    with heavy_workload("interactive"):
        nb_init = _count_radical_select(raw_query, raw_params)
        nb_apres = _count_radical_select(filtered_query, filtered_params)
    removed_rupture = max(0, nb_init - nb_apres)
    set_execution_status(
        id_campagne,
        "processing",
        target_count_initial=nb_init,
        target_count_eligible=nb_apres,
    )
    _progress(1, "Cible évaluée")
    if _cancelled():
        raise RuntimeError("job_cancelled")

    # 3) Population historique de campagne en INSERT ... SELECT.
    campagne = get_campagne(id_campagne) or campagne
    expected_state = _get_campaign_state(campagne)
    today_iso = date.today().isoformat()
    initial_action_date = (
        _norm_str(campagne.get("date_debut"))[:10]
        if expected_state == "Planifiée" and _norm_str(campagne.get("date_debut"))
        else today_iso
    )
    row_template = {
        "Nom_campagne": _norm_str(campagne.get("nom_campagne")),
        "ID_CAMPAGNE": id_campagne,
        "Etat_campagne": expected_state,
        "NB_jour_campagne": 0,
        "ID_Action": id_action_init,
        "Canal": canal_init,
        "Action": action_init,
        "Creneau": creneau_init,
        "Last_action": "",
        "Resultat_last_action": "",
        "Date_last_action": initial_action_date,
        "NB_jour_last_action": 0,
        "NB_appel": 0,
        "NB_mail": 0,
        "NB_sms": 0,
        "NB_message": 0,
        "NB_approche_commercial": 0,
        "NB_da": 0,
        "NB_cc": 0,
        "NB_push": 0,
        "date_debut_campagne": _norm_str(campagne.get("date_debut"))[:10],
        "nb_jour_debut_campagne": 0,
        "conversion": 0,
    }
    if expected_state != "En cours":
        row_template["arriv_eche"] = "Non"
    else:
        row_template["arriv_eche"] = arrive_echeance(liste_action, current_bloc_init, row_template)

    ensure_clients_campagnes_table()
    with heavy_workload("interactive"):
        inserted_clients = bulk_insert_clients_from_radical_select(
            filtered_query,
            filtered_params,
            row_template,
            # rend le job idempotent en cas de retry après crash.
            only_new=True,
        )
    set_execution_status(id_campagne, "processing", population_count=nb_apres)
    initialize_campaign_state(id_campagne, target_sync_start_seq)
    _progress(2, "Population préparée")
    try:
        from app.product_scoring.feedback import register_campaign_population
        register_campaign_population(id_campagne, _norm_str(campagne.get("id_modele")))
    except Exception:
        logger.exception("Impossible d'enregistrer le feedback produit au lancement de %s", id_campagne)

    # Si pause/annulation a eu lieu pendant l'INSERT massif, l'état maître de
    # ``campagnes`` suffit immédiatement : aucune réécriture de la population.
    campagne_after = get_campagne(id_campagne) or campagne
    current_state = _get_campaign_state(campagne_after)
    # ``clients_campagnes.Etat_campagne`` est désormais un snapshot legacy.
    if current_state == "Annulée" or _cancelled():
        raise RuntimeError("job_cancelled")

    # 4) Prépare uniquement les sorties internes. Les I/O externes Mail/Terrain
    # sont déléguées à l'Outbound Engine et ne bloquent jamais ce worker.
    mail_summary = None
    output_counts = {"crc": 0, "cc": 0, "da": 0, "cc_terrain": 0, "da_terrain": 0}
    if current_state == "En cours":
        if _cancelled():
            raise RuntimeError("job_cancelled")
        output_counts = _route_outputs_for_campaign_bulk(
            id_campagne,
            _norm_str(campagne_after.get("type_campagne")) or "sans_action_terrain",
        )
    _progress(3, "Sorties préparées")

    set_execution_status(
        id_campagne,
        "ready",
        error=None,
        finished=True,
        target_count_initial=nb_init,
        target_count_eligible=nb_apres,
        population_count=nb_apres,
    )
    if current_state == "En cours":
        try:
            from app.outbound.store import enqueue_candidates
            outbound_queued = enqueue_candidates(
                id_campagne=id_campagne,
                channels=("MAIL", "TERRAIN"),
                limit_per_channel=5000,
            )
            output_counts["outbound_mail_queued"] = int(outbound_queued.get("MAIL", 0))
            output_counts["outbound_terrain_queued"] = int(outbound_queued.get("TERRAIN", 0))
        except Exception as exc:
            output_counts["outbound_error"] = str(exc)
    _progress(4, "Campagne prête")
    return {
        "id_campagne": id_campagne,
        "nb_cible_initial": nb_init,
        "nb_apres_filtrage": nb_apres,
        "nb_exclus_rupture": removed_rupture,
        "nb_clients_insérés": int(inserted_clients),
        "etat_campagne": current_state,
        "mail_meta_loop": mail_summary,
        "output_insert": output_counts,
        "timings_ms": {"total": int((time.perf_counter() - started_at) * 1000)},
    }

def annuler_campagne(id_campagne: str) -> Dict[str, Any]:
    """
    Annule une campagne:
    - supprime côté plateforme d'animation commerciale les tiers déjà affectés
    - campagne.etat = 'Annulée'
    - l'état global reste dans campagnes.etat_campagne (aucun UPDATE massif)
    - supprime les queues internes liées à la campagne
    """
    from app.orchestration.job_store import request_cancel_for_campaign
    from app.storage.campagnes_store_sqlite import get_campagne
    previous_state = _get_campaign_state(get_campagne(id_campagne) or {})
    # Etat de gel léger : empêche immédiatement tout nouveau claim réseau.
    update_etat(id_campagne, "En pause")

    external_cancel = {"ok": True, "skipped": True, "reason": "not_called"}

    try:
        external_cancel = cancel_visits_for_campaign(
            id_campagne,
            local_status="cancelled_on_campaign_cancel",
        )
    except Exception as e:
        external_cancel = {"ok": False, "error": str(e)}

    if not external_cancel.get("ok", False) and not external_cancel.get("skipped", False):
        if previous_state:
            update_etat(id_campagne, previous_state)
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

    request_cancel_for_campaign(id_campagne)
    from app.outbound.store import cancel_for_campaign
    cancel_for_campaign(id_campagne)
    update_etat(id_campagne, "Annulée")
    set_execution_status(id_campagne, "cancelled", error=None, finished=True)

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
    - l'état global reste dans campagnes.etat_campagne (aucun UPDATE massif)
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

    # Gèle d'abord la campagne avec une seule écriture légère : producteurs et
    # workers externes cessent immédiatement de réclamer de nouveaux dispatchs.
    update_etat(id_campagne, "En pause")
    try:
        external_cancel = cancel_visits_for_campaign(
            id_campagne,
            local_status="cancelled_on_campaign_pause",
        )
    except Exception as e:
        external_cancel = {"ok": False, "error": str(e)}

    if not external_cancel.get("ok", False) and not external_cancel.get("skipped", False):
        # L'annulation externe a échoué : restaure l'état métier précédent.
        update_etat(id_campagne, etat_actuel)
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
    - met à jour uniquement l'état maître de la campagne
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

    # Si le peuplement initial est encore pris en charge par l'orchestrateur,
    # l'activation reste instantanée. Le worker lira ce nouvel état avant de
    # préparer les sorties et évite ainsi deux traitements massifs concurrents.
    execution_status = _norm_str(c.get("execution_status")) or "ready"
    if execution_status in ("preparing", "processing"):
        update_etat(id_campagne, new_etat)
        return {
            "id_campagne": id_campagne,
            "ok": True,
            "etat": new_etat,
            "preparation_pending": True,
            "new_clients_added_from_cibles": 0,
            "mail_meta_loop": None,
            "output_insert": {"crc": 0, "cc": 0, "da": 0, "cc_terrain": 0, "da_terrain": 0},
        }

    # update etats
    update_etat(id_campagne, new_etat)

    # Aucun UPDATE massif à l'activation : les compteurs de jours sont
    # désormais dérivés des dates au moment de l'évaluation du workflow.

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
            from app.targeting.incremental import sync_target_changes_for_campaign

            with heavy_workload("interactive"):
                sync_result = sync_target_changes_for_campaign(
                    id_campagne,
                    bootstrap_if_needed=True,
                    wait_for_lock=True,
                )
            if sync_result.get("ok"):
                new_clients_added = int(
                    sync_result.get("new_clients_campagne") or 0
                )
            else:
                new_clients_added = 0

        except Exception:
            new_clients_added = 0

        # Les actions externes seront publiées dans l'outbox après la
        # reconstruction des sorties internes; aucun appel réseau ici.

        # Reconstruction bulk des queues.
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

        try:
            from app.outbound.store import enqueue_candidates, resume_paused_for_campaign
            resume_paused_for_campaign(id_campagne)
            queued_external = enqueue_candidates(
                id_campagne=id_campagne,
                channels=("MAIL", "TERRAIN"),
                limit_per_channel=5000,
            )
            output_counts["outbound_mail_queued"] = int(queued_external.get("MAIL", 0))
            output_counts["outbound_terrain_queued"] = int(queued_external.get("TERRAIN", 0))
        except Exception as exc:
            output_counts["outbound_error"] = str(exc)

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

def sync_new_clients_from_cible_for_campaign(
    conn: RuntimeConnection | None,
    id_campagne: str,
    *,
    candidate_radicals: Sequence[str] | None = None,
) -> Dict[str, Any]:
    """
    Synchronisation insert-only de la cible vers la campagne.

    Si ``candidate_radicals`` est fourni, PostgreSQL n'évalue les filtres que
    sur ce lot de clients modifiés. Sans candidat, le comportement historique
    de rescan complet reste disponible pour le bootstrap et la préparation.

    Les cibles internes (DB ou fichier matérialisé) utilisent INSERT ... SELECT
    directement dans PostgreSQL. Les datamarts externes sont volontairement
    réservés au moteur d'orchestration externe et ne sont jamais copiés ici.
    """
    from app.storage.campagnes_store_sqlite import get_campagne
    from app.storage.clients_cibles_store_sqlite import (
        insert_only_members_from_radical_select,
        update_cible_volume_if_column_exists,
    )
    from app.domain.workflow_nav import is_objective_bloc

    _ = conn  # conservé dans la signature pour compatibilité avec le batch

    c = get_campagne(id_campagne) or {}
    data_source_code = _norm_str(c.get("data_source_code")) or "internal"
    if data_source_code != "internal":
        return {
            "ok": False,
            "error": "external_data_source_requires_orchestrator",
            "new_cible_members": 0,
            "new_clients_campagne": 0,
        }
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
    creneau_init = normalize_creneau(root.get("Creneau"))
    if is_objective_bloc(root):
        canal_init = "Objectif"
        action_init = "Objectif"
        creneau_init = "Indifferent"

    current_bloc_init = find_bloc_by_id(liste_action, id_action_init) or root
    campagne_state = _get_campaign_state(c) or "En cours"
    sync_action_date = (
        _norm_str(c.get("date_debut") or "")[:10]
        if campagne_state == "Planifiée" and _norm_str(c.get("date_debut") or "")
        else date.today().isoformat()
    )

    row_template = {
        "Nom_campagne": _norm_str(c.get("nom_campagne") or c.get("Nom_campagne")),
        "ID_CAMPAGNE": id_campagne,
        "Etat_campagne": campagne_state,
        "NB_jour_campagne": 0,
        "ID_Action": id_action_init,
        "Canal": canal_init,
        "Action": action_init,
        "Creneau": creneau_init,
        "Last_action": "",
        "Resultat_last_action": "",
        "Date_last_action": sync_action_date,
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
        candidate_radicals=candidate_radicals,
    )

    if db_select is None:
        return {
            "ok": False,
            "error": "no_native_target_path",
            "new_cible_members": 0,
            "new_clients_campagne": 0,
        }

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
    if int(inserted or 0) > 0:
        try:
            from app.product_scoring.feedback import register_campaign_population
            register_campaign_population(id_campagne, id_modele)
        except Exception:
            logger.exception("Impossible d'enregistrer le feedback produit incrémental de %s", id_campagne)
    return {
        "ok": True,
        "new_cible_members": int(new_cible),
        "new_clients_campagne": int(inserted),
    }
