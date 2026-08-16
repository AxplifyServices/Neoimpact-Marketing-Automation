# app/scripts/batch_manuel.py
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from app.storage.runtime_db import RuntimeConnection, connect_runtime
from app.storage.postgres_db import get_column_names, table_exists
from app.storage.campagnes_store_sqlite import list_all_campagnes, update_etat
from app.storage.clients_campagnes_store_sqlite import (
    ensure_table as ensure_clients_campagnes,
    set_clients_etat_for_campagne,
)

from app.domain.campagne_service import sync_new_clients_from_cible_for_campaign

# outputs (phase 1)
from app.storage.crc_input_store_sqlite import (
    ensure_crc_input_table,
    clear_crc_input,
    fill_crc_input_from_clients_campagnes,
)
from app.storage.action_vers_da_store_sqlite import (
    ensure_vers_da_table,
    fill_action_vers_da_from_clients_campagnes,
)
from app.storage.action_vers_cc_store_sqlite import (
    ensure_vers_cc_table,
    fill_action_vers_cc_from_clients_campagnes,
)

from app.engine.traitement_mail_engine import run_mail_meta_loop

# ✅ NEW workflow nav (nouvelle logique objectif)
from app.domain.workflow_nav import (
    find_bloc_by_id,
    pick_next_child,
    arrive_echeance,
    is_objective_bloc,
    objective_branch,
)

from app.domain.terrain_visit_webhook import dispatch_pending_visits_for_campaign

CLIENTS_CAMPAGNES_TABLE = "clients_campagnes"
CAMPAGNES_TABLE = "campagnes"
MODELES_TABLE = "modeles"
CLIENTS_TABLE = "clients"


# =========================================================
# Helpers
# =========================================================
def _connect() -> RuntimeConnection:
    return connect_runtime()


def _norm_str(x: Any) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    return "" if s.lower() == "none" else s

def _get_campaign_state(campagne: Dict[str, Any]) -> str:
    """
    Retourne l'état d'une campagne, quel que soit le nom historique
    utilisé pour la colonne.

    La colonne officielle actuelle de la table campagnes est :
    Etat_campagne
    """
    if not isinstance(campagne, dict):
        return ""

    return _norm_str(
        campagne.get("Etat_campagne")
        or campagne.get("etat_campagne")
        or campagne.get("etat")
    )

def _norm_cmp(x: Any) -> str:
    s = _norm_str(x).lower()
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_iso_date(x: Any) -> Optional[date]:
    t = _norm_str(x)
    if not t:
        return None
    try:
        return date.fromisoformat(t[:10])
    except Exception:
        return None


def _safe_json_loads(s: str, default: Any) -> Any:
    try:
        return json.loads(s)
    except Exception:
        return default


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clients_columns(conn: RuntimeConnection) -> List[str]:
    return get_column_names(CLIENTS_TABLE)


def _cc_columns(conn: RuntimeConnection) -> List[str]:
    return get_column_names(CLIENTS_CAMPAGNES_TABLE)


def _cc_has_col(conn: RuntimeConnection, col: str) -> bool:
    return col in set(_cc_columns(conn))

def _table_exists(
    conn: RuntimeConnection,
    table_name: str,
) -> bool:
    normalized_table_name = _norm_str(table_name)
    return bool(
        normalized_table_name
        and table_exists(normalized_table_name)
    )

def _recompute_nb_jour_debut_campagne(conn: RuntimeConnection) -> int:
    """
    Met à jour nb_jour_debut_campagne = today - date_debut_campagne (en jours).
    - Ne casse pas si colonnes absentes.
    - Pour les anciennes campagnes où date_debut_campagne est vide => on ne touche pas.
    """
    if not _cc_has_col(conn, "date_debut_campagne") or not _cc_has_col(conn, "nb_jour_debut_campagne"):
        return 0

    today_iso = date.today().isoformat()
    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE {CLIENTS_CAMPAGNES_TABLE}
        SET nb_jour_debut_campagne = CASE
            WHEN COALESCE(date_debut_campagne,'') = '' THEN nb_jour_debut_campagne
            ELSE (?::date - SUBSTRING(date_debut_campagne FROM 1 FOR 10)::date)
        END
        WHERE COALESCE(Etat_campagne,'') IN ('En cours','Planifiée','En pause')
        """,
        (today_iso,),
    )
    return int(cur.rowcount or 0)


def _resolve_clients_col(conn: RuntimeConnection, requested_col: str) -> Optional[str]:
    """
    Résout une colonne de la table clients de manière robuste:
    - match exact
    - sinon match insensible à la casse/accents/espaces via _norm_cmp
    Retourne le NOM réel de la colonne dans la DB.
    """
    req = _norm_str(requested_col)
    if not req:
        return None

    cols = _clients_columns(conn)
    if req in cols:
        return req

    req_n = _norm_cmp(req)
    for c in cols:
        if _norm_cmp(c) == req_n:
            return c

    return None


def _modeles_id_col(conn: RuntimeConnection) -> str:
    cols = get_column_names(MODELES_TABLE)
    if "id_modele" in cols:
        return "id_modele"
    if "ID_MODELE" in cols:
        return "ID_MODELE"
    return "id_modele"


def _modeles_cols(conn: RuntimeConnection) -> List[str]:
    return get_column_names(MODELES_TABLE)


def _load_client_row_by_radical(conn: RuntimeConnection, radical_compte: str) -> Dict[str, Any]:
    """Charge la ligne clients.* pour un radical_compte. Retourne {} si introuvable."""
    rc = _norm_str(radical_compte)
    if not rc:
        return {}
    cur = conn.cursor()

    resolved = _resolve_clients_col(conn, "radical_compte") or "radical_compte"
    try:
        cur.execute(f'SELECT * FROM {CLIENTS_TABLE} WHERE "{resolved}" = ? LIMIT 1', (rc,))
    except Exception:
        return {}

    row = cur.fetchone()
    if not row:
        return {}
    return dict(row)


def _inject_client_fields(row_clients_campagnes: Dict[str, Any], client_row: Dict[str, Any]) -> Dict[str, Any]:
    """Enrichit une ligne clients_campagnes avec clients.* + client.<col> (et alias compact)."""
    if not isinstance(row_clients_campagnes, dict) or not isinstance(client_row, dict):
        return row_clients_campagnes

    def _add_key(key: str, value: Any) -> None:
        if key and key not in row_clients_campagnes:
            row_clients_campagnes[key] = value
        key_compact = re.sub(r"\s+", "", key)
        if key_compact and key_compact not in row_clients_campagnes:
            row_clients_campagnes[key_compact] = value

    for k, v in client_row.items():
        if k not in row_clients_campagnes:
            row_clients_campagnes[k] = v

        _add_key(f"client.{k}", v)
        _add_key(str(k), v)

    return row_clients_campagnes


# =========================================================
# Batch steps (ordre imposé)
# =========================================================
def _list_active_campaigns(
    campagnes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Retourne les campagnes devant être prises en charge par le batch.

    États concernés :
    - En cours
    - Planifiée
    - En pause

    Une campagne en pause reste chargée pour les traitements techniques
    compatibles, mais ne doit pas être routée comme une campagne en cours.
    """
    active_campaigns: List[Dict[str, Any]] = []

    for campagne in campagnes:
        etat = _get_campaign_state(campagne)

        if etat in ("En cours", "Planifiée", "En pause"):
            active_campaigns.append(campagne)

    return active_campaigns


def _load_modele_meta(conn: RuntimeConnection, id_modele: str) -> Tuple[List[Dict[str, Any]]]:
    """
    ✅ Robustesse: variable_cible et objectif peuvent ne plus exister.
    Retourne toujours (variable_cible, objectif, liste_action) mais variable_cible/objectif peuvent être ''.
    """
    id_col = _modeles_id_col(conn)
    cols = set(_modeles_cols(conn))

    select_cols = []
    # liste_action doit exister ; si pas, on retourne []
    if "liste_action" in cols:
        select_cols.append("liste_action")

    if "liste_action" not in cols:
        return  []
    cur = conn.cursor()
    cur.execute(
        f"SELECT {', '.join(select_cols)} FROM {MODELES_TABLE} WHERE {id_col} = ?",
        (id_modele,),
    )
    r = cur.fetchone()
    if not r:
        return []

    raw = r["liste_action"]
    if isinstance(raw, list):
        liste_action = raw
    else:
        liste_action = _safe_json_loads(_norm_str(raw), [])
        if not isinstance(liste_action, list):
            liste_action = []

    return liste_action


def _cancel_if_rupture_relation(conn: RuntimeConnection, id_campagne: str) -> int:
    """
    Si un client est en 'Rupture de relation' (dans clients),
    on le sort de la campagne :
      - Etat_campagne = 'Canceled' (si la colonne existe)
      - Canal = 'Canceled' (si la colonne existe)
      - Action = 'Canceled' (si la colonne existe)

    Objectif : ne plus router / avancer / envoyer des mails à ces clients.
    """
    cols_clients = set(_clients_columns(conn))
    if "STATUT_CLIENT" not in cols_clients and "statut_client" not in cols_clients:
        return 0
    statut_col = "STATUT_CLIENT" if "STATUT_CLIENT" in cols_clients else "statut_client"

    # Construire un SET dynamique selon les colonnes réellement présentes dans clients_campagnes
    set_parts = []
    if _cc_has_col(conn, "Etat_campagne"):
        set_parts.append("Etat_campagne = 'Canceled'")
    if _cc_has_col(conn, "Canal"):
        set_parts.append("Canal = 'Canceled'")
    if _cc_has_col(conn, "Action"):
        set_parts.append("Action = 'Canceled'")

    # Si aucune de ces colonnes n'existe, on ne peut rien faire
    if not set_parts:
        return 0

    set_sql = ", ".join(set_parts)

    # Ne pas re-canceler si déjà canceled (si Etat_campagne existe)
    extra_where = ""
    if _cc_has_col(conn, "Etat_campagne"):
        extra_where = " AND COALESCE(Etat_campagne,'') <> 'Canceled' "

    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE {CLIENTS_CAMPAGNES_TABLE}
        SET {set_sql}
        WHERE ID_CAMPAGNE = ?
          AND COALESCE(Etat_campagne,'') IN ('En cours','Planifiée','En pause')
          {extra_where}
          AND EXISTS (
              SELECT 1
              FROM {CLIENTS_TABLE} cl
              WHERE cl.radical_compte = {CLIENTS_CAMPAGNES_TABLE}.Radical_compte
                AND LOWER(TRIM(COALESCE(cl."{statut_col}",''))) = LOWER('Rupture de relation')
          )
        """,
        (id_campagne,),
    )
    return int(cur.rowcount or 0)



def _update_campaigns_status_from_dates(
    campagnes: List[Dict[str, Any]],
) -> Dict[str, int]:
    """
    Met à jour automatiquement l'état des campagnes selon leurs dates.

    Règles :
    - Planifiée et date courante comprise entre début et fin -> En cours
    - En cours et date de fin dépassée -> Terminée
    - En pause -> aucun changement automatique
    - Annulée ou Terminée -> aucun changement
    """
    today = date.today()

    counts = {
        "to_en_cours": 0,
        "to_terminee": 0,
        "invalid_dates": 0,
    }

    for campagne in campagnes:
        id_campagne = _norm_str(campagne.get("id_campagne"))
        etat = _get_campaign_state(campagne)
        date_debut = _parse_iso_date(campagne.get("date_debut"))
        date_fin = _parse_iso_date(campagne.get("date_fin"))

        if not id_campagne:
            continue

        if etat in ("Annulée", "Terminée"):
            continue

        if etat == "En pause":
            continue

        if not date_debut or not date_fin:
            counts["invalid_dates"] += 1
            continue

        if date_fin < date_debut:
            counts["invalid_dates"] += 1
            continue

        if etat == "Planifiée" and date_debut <= today <= date_fin:
            update_etat(id_campagne, "En cours")
            set_clients_etat_for_campagne(id_campagne, "En cours")
            counts["to_en_cours"] += 1
            continue

        if etat == "En cours" and date_fin < today:
            update_etat(id_campagne, "Terminée")
            set_clients_etat_for_campagne(id_campagne, "Terminée")
            counts["to_terminee"] += 1

    return counts


def _recompute_nb_jour_last_action(conn: RuntimeConnection) -> int:
    today_iso = date.today().isoformat()
    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE {CLIENTS_CAMPAGNES_TABLE}
        SET NB_jour_last_action = CASE
            WHEN COALESCE(Date_last_action,'') = '' THEN 0
            ELSE (?::date - SUBSTRING(Date_last_action FROM 1 FOR 10)::date)
        END
        WHERE COALESCE(Etat_campagne,'') IN ('En cours','Planifiée', 'En pause')
        """,
        (today_iso,),
    )
    return int(cur.rowcount or 0)


def _advance_en_attente_rows(conn: RuntimeConnection, id_campagne: str, liste_action: List[Dict[str, Any]]) -> int:
    """
    ✅ NEW:
    - Traite Action IN ('En attente', 'Objectif') pour re-tester les blocs objectifs
    - Si bloc courant est objectif:
        * Canal='Objectif' et Action='Objectif'
        * Si branche Oui => conversion=1 (sans écraser si déjà 1)
    - Navigation via pick_next_child (nouveau workflow_nav)
    - Si aucune transition possible => Action='En attente' (on reteste à la prochaine itération)
    """
    if not isinstance(liste_action, list) or len(liste_action) == 0:
        return 0

    has_conversion = _cc_has_col(conn, "conversion")
    cur = conn.cursor()

    # ✅ NEW: inclure Objectif
    cur.execute(
        f"""
        SELECT rowid as __rid, *
        FROM {CLIENTS_CAMPAGNES_TABLE}
        WHERE ID_CAMPAGNE = ?
          AND COALESCE(Etat_campagne,'') IN ('En cours','Planifiée', 'En pause')
          AND COALESCE(Action,'') IN ('En attente', 'Objectif')
        """,
        (id_campagne,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    changed = 0

    _client_cache: Dict[str, Dict[str, Any]] = {}

    for r in rows:
        rid = int(r["__rid"])
        id_action = _norm_str(r.get("ID_Action"))

        # enrich clients.* (conditions navigation + objectif)
        rc = _norm_str(r.get("Radical_compte") or r.get("radical_compte"))
        if rc:
            if rc not in _client_cache:
                _client_cache[rc] = _load_client_row_by_radical(conn, rc)
            _inject_client_fields(r, _client_cache.get(rc, {}))

        current = find_bloc_by_id(liste_action, id_action)
        if not current:
            continue

        # ✅ NEW: si bloc objectif -> Canal/Action = Objectif ET on resynchronise ID_Action
        if is_objective_bloc(current):
            cur_id = _norm_str(current.get("ID")) or id_action  # fallback sécurité

            # Update en 1 seule requête (évite Canal/Action sans ID_Action)
            if (_cc_has_col(conn, "ID_Action") and _norm_str(r.get("ID_Action")) != cur_id) or \
               (_cc_has_col(conn, "Canal") and _norm_str(r.get("Canal")) != "Objectif") or \
               (_cc_has_col(conn, "Action") and _norm_str(r.get("Action")) != "Objectif"):

                set_parts = []
                params = []

                if _cc_has_col(conn, "ID_Action"):
                    set_parts.append("ID_Action = ?")
                    params.append(cur_id)

                if _cc_has_col(conn, "Canal"):
                    set_parts.append("Canal = 'Objectif'")

                if _cc_has_col(conn, "Action"):
                    set_parts.append("Action = 'Objectif'")

                sql = f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET " + ", ".join(set_parts) + " WHERE rowid=?"
                params.append(rid)

                cur.execute(sql, params)
                changed += int(cur.rowcount or 0)

                # garder r cohérent pour la suite du traitement
                r["ID_Action"] = cur_id
                r["Canal"] = "Objectif"
                r["Action"] = "Objectif"

            # Si objectifs validés => conversion=1 (si colonne existe)
            if has_conversion:
                branch = objective_branch(current, r)  # 'Oui' / 'Non'
                if branch == "Oui":
                    try:
                        conv_val = int(r.get("conversion") or 0)
                    except Exception:
                        conv_val = 0
                    if conv_val != 1:
                        cur.execute(
                            f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET conversion=1 WHERE rowid=? AND COALESCE(conversion,0) <> 1",
                            (rid,),
                        )
                        changed += int(cur.rowcount or 0)
                        r["conversion"] = 1


        # ✅ Navigation (normal ou objectif) via nouveau workflow_nav
        nxt = pick_next_child(liste_action, current, r)

        if not nxt:
            # ✅ NEW: si aucune condition pour changer de bloc -> action en attente
            if _cc_has_col(conn, "Action") and _norm_str(r.get("Action")) != "En attente":
                cur.execute(
                    f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET Action='En attente' WHERE rowid=?",
                    (rid,),
                )
                changed += int(cur.rowcount or 0)
            continue

        new_id = _norm_str(nxt.get("ID"))

        # Si le prochain bloc est objectif -> Canal/Action doivent devenir Objectif
        if is_objective_bloc(nxt):
            new_canal = "Objectif"
            new_action = "Objectif"
        else:
            new_canal = _norm_str(nxt.get("Canal"))
            new_action = _norm_str(nxt.get("Action"))

        if not new_id or not new_action:
            continue

        cur.execute(
            f"""
            UPDATE {CLIENTS_CAMPAGNES_TABLE}
            SET ID_Action = ?, Canal = ?, Action = ?
            WHERE rowid = ?
            """,
            (new_id, new_canal, new_action, rid),
        )
        changed += int(cur.rowcount or 0)

    return int(changed)


def _update_arriv_eche_for_campaign(
    conn: RuntimeConnection,
    id_campagne: str,
    liste_action: List[Dict[str, Any]],
) -> int:
    """
    Met à jour clients_campagnes.arriv_eche ('Oui'/'Non') pour une campagne.
    - si Action == 'Closed' => arriv_eche = 'Non'
    - sinon calcule via arrive_echeance(liste_action, bloc_courant, row)
    """
    if not id_campagne or not isinstance(liste_action, list) or len(liste_action) == 0:
        return 0
    cur = conn.cursor()

    cur.execute(
        f"""
        SELECT rowid as __rid, ID_Action, Action, Etat_campagne, Resultat_last_action, NB_jour_last_action, arriv_eche
        FROM {CLIENTS_CAMPAGNES_TABLE}
        WHERE ID_CAMPAGNE = ?
          AND COALESCE(Etat_campagne,'') IN ('En cours','Planifiée','En pause')
        """,
        (id_campagne,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    changed = 0

    for r in rows:
        rid = int(r.get("__rid") or 0)
        if rid <= 0:
            continue

        action = _norm_str(r.get("Action"))
        if action == "Closed":
            new_flag = "Non"
        else:
            id_action = _norm_str(r.get("ID_Action"))
            current = find_bloc_by_id(liste_action, id_action)
            if not current:
                new_flag = "Non"
            else:
                new_flag = arrive_echeance(liste_action, current, r)

        if _norm_str(r.get("arriv_eche")) != _norm_str(new_flag):
            cur.execute(
                f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET arriv_eche = ? WHERE rowid = ?",
                (new_flag, rid),
            )
            changed += int(cur.rowcount or 0)

    return int(changed)


def _rebuild_outputs_for_all_en_cours(conn: RuntimeConnection, campagnes: List[Dict[str, Any]]) -> Dict[str, int]:
    ensure_crc_input_table()
    ensure_vers_da_table()
    ensure_vers_cc_table()

    clear_crc_input()
    cur = conn.cursor()
    cur.execute("DELETE FROM vers_da")
    cur.execute("DELETE FROM vers_cc")

    # Anciennes queues terrain : on les vide, elles ne servent plus.
    cur.execute("DELETE FROM vers_da_terrain") if _table_exists(conn, "vers_da_terrain") else None
    cur.execute("DELETE FROM vers_cc_terrain") if _table_exists(conn, "vers_cc_terrain") else None

    conn.commit()

    n_crc = 0
    n_da = 0
    n_cc = 0
    n_external_sent = 0
    n_external_errors = 0

    for c in campagnes:
        etat = _get_campaign_state(c)

        if etat != "En cours":
            continue

        id_c = _norm_str(c.get("id_campagne"))
        if not id_c:
            continue

        type_campagne = _norm_str(c.get("type_campagne")) or "sans_action_terrain"

        n_crc += int(fill_crc_input_from_clients_campagnes(id_c) or 0)

        if type_campagne == "avec_action_terrain":
            dispatch = dispatch_pending_visits_for_campaign(id_c)
            n_external_sent += int(dispatch.get("sent") or 0)
            n_external_errors += int(dispatch.get("errors") or 0)
        else:
            n_da += int(fill_action_vers_da_from_clients_campagnes(id_c) or 0)
            n_cc += int(fill_action_vers_cc_from_clients_campagnes(id_c) or 0)

    return {
        "crc_input": n_crc,
        "vers_da": n_da,
        "vers_cc": n_cc,
        "external_visit_sent": n_external_sent,
        "external_visit_errors": n_external_errors,
    }

# =========================================================
# Public (lié au bouton refresh)
# =========================================================
def run_batch_manuel() -> Dict[str, Any]:
    """
    Ordre EXACT demandé + ajout:
    - traitement mails après MAJ/advance et avant rebuild outputs
    - sync nouveaux clients depuis cible (INSERT ONLY)
    """
    ensure_clients_campagnes()

    campagnes = list_all_campagnes()
    actives = _list_active_campaigns(campagnes)

    out: Dict[str, Any] = {
        "statut_actuel_updated": 0,
        "rupture_canceled": 0,
        "campagnes_status": {"to_en_cours": 0, "to_terminee": 0},
        "nb_jour_last_action_updated": 0,
        "nb_jour_debut_campagne_updated": 0,
        "arriv_eche_updated": 0,
        "en_attente_advanced": 0,

        # ⚠️ legacy KPI conservé pour ne pas casser l'UI (désormais toujours 0)
        "closed_objectif": 0,

        "new_clients_added_from_cibles": 0,
        "new_cible_members": 0,
        "target_sync": {
            "campaigns_processed": 0,
            "campaigns_succeeded": 0,
            "campaigns_failed": 0,
            "details": [],
        },
        "mails_processed": None,
        "outputs_rebuilt": {"crc_input": 0, "vers_da": 0, "vers_cc": 0},
    }

    conn = _connect()
    try:
        # 1) update statut_actuel from clients variable_cible (par campagne)
        for c in actives:
            id_c = _norm_str(c.get("id_campagne"))
            id_modele = _norm_str(c.get("id_modele"))
            if not id_c or not id_modele:
                continue

            # 2) rupture relation -> canceled
            out["rupture_canceled"] += _cancel_if_rupture_relation(conn, id_c)

        conn.commit()

        # 3) update campagnes statuses
        out["campagnes_status"] = _update_campaigns_status_from_dates(campagnes)

        campagnes = list_all_campagnes()
        actives = _list_active_campaigns(campagnes)

        # 4) recompute NB_jour_last_action
        out["nb_jour_last_action_updated"] = _recompute_nb_jour_last_action(conn)

        # recompute nb_jour_debut_campagne
        out["nb_jour_debut_campagne_updated"] = _recompute_nb_jour_debut_campagne(conn)

        conn.commit()

        # 5) advance En attente / Objectif (nouvelle logique)
        for c in actives:
            id_c = _norm_str(c.get("id_campagne"))
            id_modele = _norm_str(c.get("id_modele"))
            if not id_c or not id_modele:
                continue

            liste_action = _load_modele_meta(conn, id_modele)
            out["en_attente_advanced"] += _advance_en_attente_rows(conn, id_c, liste_action)

        conn.commit()

        # 5.5) Synchronisation insert-only :
        # cible dynamique -> clients_cibles -> clients_campagnes
        for campagne in actives:
            id_campagne = _norm_str(campagne.get("id_campagne"))

            if not id_campagne:
                continue

            out["target_sync"]["campaigns_processed"] += 1

            try:
                result = sync_new_clients_from_cible_for_campaign(
                    conn,
                    id_campagne,
                )

                detail = {
                    "id_campagne": id_campagne,
                    "etat": _get_campaign_state(campagne),
                    "ok": bool(result.get("ok")),
                    "new_cible_members": int(
                        result.get("new_cible_members") or 0
                    ),
                    "new_clients_campagne": int(
                        result.get("new_clients_campagne") or 0
                    ),
                }

                if result.get("ok"):
                    out["target_sync"]["campaigns_succeeded"] += 1

                    out["new_cible_members"] += detail[
                        "new_cible_members"
                    ]

                    out["new_clients_added_from_cibles"] += detail[
                        "new_clients_campagne"
                    ]

                    conn.commit()
                else:
                    out["target_sync"]["campaigns_failed"] += 1
                    detail["error"] = _norm_str(
                        result.get("error")
                        or "Erreur de synchronisation non précisée"
                    )

                out["target_sync"]["details"].append(detail)

            except Exception as exc:
                conn.rollback()

                out["target_sync"]["campaigns_failed"] += 1
                out["target_sync"]["details"].append(
                    {
                        "id_campagne": id_campagne,
                        "etat": _get_campaign_state(campagne),
                        "ok": False,
                        "new_cible_members": 0,
                        "new_clients_campagne": 0,
                        "error": str(exc),
                    }
                )

        # 5bis) update arriv_eche (après recompute NB_jour_last_action et advance)
        for c in actives:
            id_c = _norm_str(c.get("id_campagne"))
            id_modele = _norm_str(c.get("id_modele"))
            if not id_c or not id_modele:
                continue

            liste_action2 = _load_modele_meta(conn, id_modele)
            out["arriv_eche_updated"] += _update_arriv_eche_for_campaign(conn, id_c, liste_action2)

        conn.commit()

        # traiter mails (après mises à jour/advance)
        out["mails_processed"] = run_mail_meta_loop(max_passes=10, limit_rows_per_pass=5000)

        # 6) rebuild outputs
        out["outputs_rebuilt"] = _rebuild_outputs_for_all_en_cours(conn, campagnes)

    finally:
        conn.close()

    return out
