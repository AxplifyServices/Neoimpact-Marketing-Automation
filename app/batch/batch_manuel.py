# app/batch/batch_manuel.py
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from app.storage.runtime_db import RuntimeConnection, connect_runtime
from app.core.workload_governor import heavy_workload
from app.storage.postgres_db import get_column_names, table_exists
from app.storage.campagnes_store_sqlite import list_all_campagnes, update_etat
from app.storage.clients_campagnes_store_sqlite import (
    ensure_table as ensure_clients_campagnes,
)

from app.targeting.incremental import sync_target_changes_for_campaign
from app.targeting.store import prune_processed_changes
from app.domain.conversion_service import mark_converted, record_objective_entry
from app.best_channel.history import finalize_current_sequence
from app.domain.send_time import normalize_creneau

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

from app.domain.workflow_nav import (
    find_bloc_by_id,
    pick_next_child,
    arrive_echeance,
    is_objective_bloc,
    objective_branch,
)

from app.domain.terrain_visit_webhook import cancel_visits_for_campaign

CLIENTS_CAMPAGNES_TABLE = "clients_campagnes"
CAMPAGNES_TABLE = "campagnes"
MODELES_TABLE = "modeles"
CLIENTS_TABLE = "clients"
BATCH_ROW_CHUNK_SIZE = max(50, int(os.getenv("BATCH_ROW_CHUNK_SIZE", "500")))


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
    s = "".join(
        ch
        for ch in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(ch)
    )
    return re.sub(r"\s+", " ", s).strip()


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
    """Compatibilité : compteur désormais calculé à la demande.

    Avant la migration 013, le batch réécrivait toutes les lignes actives
    chaque jour. ``workflow_nav`` dérive maintenant ce nombre depuis
    ``date_debut_campagne`` ; aucun UPDATE global n'est nécessaire.
    """
    return 0


def _resolve_clients_col(
    conn: RuntimeConnection,
    requested_col: str,
) -> Optional[str]:
    req = _norm_str(requested_col)
    if not req:
        return None

    cols = _clients_columns(conn)
    if req in cols:
        return req

    req_n = _norm_cmp(req)
    for col in cols:
        if _norm_cmp(col) == req_n:
            return col

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


def _load_client_row_by_radical(
    conn: RuntimeConnection,
    radical_compte: str,
) -> Dict[str, Any]:
    rc = _norm_str(radical_compte)
    if not rc:
        return {}

    cur = conn.cursor()
    resolved = _resolve_clients_col(conn, "radical_compte") or "radical_compte"

    try:
        cur.execute(
            f'SELECT * FROM {CLIENTS_TABLE} WHERE "{resolved}" = ? LIMIT 1',
            (rc,),
        )
    except Exception:
        return {}

    row = cur.fetchone()
    return dict(row) if row else {}


def _inject_client_fields(
    row_clients_campagnes: Dict[str, Any],
    client_row: Dict[str, Any],
) -> Dict[str, Any]:
    if (
        not isinstance(row_clients_campagnes, dict)
        or not isinstance(client_row, dict)
    ):
        return row_clients_campagnes

    def _add_key(key: str, value: Any) -> None:
        if key and key not in row_clients_campagnes:
            row_clients_campagnes[key] = value
        key_compact = re.sub(r"\s+", "", key)
        if key_compact and key_compact not in row_clients_campagnes:
            row_clients_campagnes[key_compact] = value

    for key, value in client_row.items():
        if key not in row_clients_campagnes:
            row_clients_campagnes[key] = value
        _add_key(f"client.{key}", value)
        _add_key(str(key), value)

    return row_clients_campagnes


# =========================================================
# Batch steps
# =========================================================
def _list_active_campaigns(
    campagnes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Seules les campagnes En cours doivent progresser dans le workflow.
    """
    return [
        campagne
        for campagne in campagnes
        if _get_campaign_state(campagne) == "En cours"
        and _norm_str(campagne.get("execution_status") or "ready") == "ready"
    ]


def _load_modele_meta(
    conn: RuntimeConnection,
    id_modele: str,
) -> List[Dict[str, Any]]:
    id_col = _modeles_id_col(conn)
    cols = set(_modeles_cols(conn))

    if "liste_action" not in cols:
        return []

    cur = conn.cursor()
    cur.execute(
        f"SELECT liste_action FROM {MODELES_TABLE} WHERE {id_col} = ?",
        (id_modele,),
    )

    row = cur.fetchone()
    if not row:
        return []

    raw = row["liste_action"]
    if isinstance(raw, list):
        return raw

    liste_action = _safe_json_loads(_norm_str(raw), [])
    return liste_action if isinstance(liste_action, list) else []


def _cancel_if_rupture_relation(
    conn: RuntimeConnection,
    id_campagne: str,
) -> int:
    """
    Neutralise uniquement la participation du client à la campagne
    lorsqu'il est en Rupture de relation.
    """
    cols_clients = set(_clients_columns(conn))
    if (
        "STATUT_CLIENT" not in cols_clients
        and "statut_client" not in cols_clients
    ):
        return 0

    statut_col = (
        "STATUT_CLIENT"
        if "STATUT_CLIENT" in cols_clients
        else "statut_client"
    )

    set_parts: List[str] = ["row_status = 1"]
    if _cc_has_col(conn, "Etat_campagne"):
        # Snapshot legacy conservé uniquement pour les anciens écrans/outils.
        set_parts.append("Etat_campagne = 'Canceled'")
    if _cc_has_col(conn, "Canal"):
        set_parts.append("Canal = 'Canceled'")
    if _cc_has_col(conn, "Action"):
        set_parts.append("Action = 'Canceled'")

    if not set_parts:
        return 0

    extra_where = " AND COALESCE(row_status,0) = 0 "

    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE {CLIENTS_CAMPAGNES_TABLE}
        SET {', '.join(set_parts)}
        WHERE ID_CAMPAGNE = ?
          {extra_where}
          AND EXISTS (
              SELECT 1
              FROM {CLIENTS_TABLE} cl
              WHERE cl.radical_compte = {CLIENTS_CAMPAGNES_TABLE}.Radical_compte
                AND LOWER(TRIM(COALESCE(cl."{statut_col}",'')))
                    = LOWER('Rupture de relation')
          )
        """,
        (id_campagne,),
    )
    return int(cur.rowcount or 0)


def _delete_outputs_for_campagne(
    id_campagne: str,
) -> None:
    """
    Supprime les sorties opérationnelles locales d'une campagne inactive.
    """
    id_campagne = _norm_str(id_campagne)
    if not id_campagne:
        return

    conn = _connect()
    try:
        cur = conn.cursor()

        for table_name in (
            "crc_input",
            "vers_cc",
            "vers_da",
            "vers_cc_terrain",
            "vers_da_terrain",
        ):
            if not _table_exists(conn, table_name):
                continue

            cur.execute(
                f"DELETE FROM {table_name} WHERE ID_CAMPAGNE = ?",
                (id_campagne,),
            )

        conn.commit()
    finally:
        conn.close()


def _update_campaigns_status_from_dates(
    campagnes: List[Dict[str, Any]],
) -> Dict[str, int]:
    """
    Règles temporelles :
    - Planifiée avant début : reste Planifiée.
    - Planifiée pendant sa fenêtre : En cours.
    - Planifiée après sa fin : Terminée.
    - En cours après sa fin : Terminée.
    - En pause : gelée.
    - Annulée / Terminée : aucun changement.
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

        # Planifiée mais toute la fenêtre est déjà passée.
        if etat == "Planifiée" and date_fin < today:
            update_etat(id_campagne, "Terminée")

            try:
                _delete_outputs_for_campagne(id_campagne)
            except Exception:
                pass

            counts["to_terminee"] += 1
            continue

        # Démarrage automatique.
        if etat == "Planifiée" and date_debut <= today <= date_fin:
            update_etat(id_campagne, "En cours")

            # Aucun UPDATE massif des clients : pour une campagne planifiée,
            # Date_last_action est initialisée à date_debut dès le peuplement et
            # les compteurs de jours sont calculés dynamiquement.

            counts["to_en_cours"] += 1
            continue

        # Fin automatique d'une campagne déjà démarrée.
        if etat == "En cours" and date_fin < today:
            try:
                cancel_visits_for_campaign(
                    id_campagne,
                    local_status="cancelled_on_campaign_end",
                )
            except Exception:
                pass

            update_etat(id_campagne, "Terminée")

            try:
                _delete_outputs_for_campagne(id_campagne)
            except Exception:
                pass

            counts["to_terminee"] += 1

    return counts


def _recompute_nb_jour_last_action(conn: RuntimeConnection) -> int:
    """Compatibilité : compteur désormais calculé depuis Date_last_action."""
    return 0


def _advance_en_attente_rows(
    conn: RuntimeConnection,
    id_campagne: str,
    liste_action: List[Dict[str, Any]],
) -> int:
    """
    Fait progresser les lignes En attente/Objectif avec une mémoire bornée.

    L'ancienne version chargeait toute la campagne avec ``fetchall()`` et
    ``to_jsonb(cl)``. Une campagne de plusieurs centaines de milliers de
    clients pouvait donc occuper plusieurs Go de RAM Python.

    Cette version utilise une pagination keyset sur la PK technique et commit
    entre les lots. Le slot batch est relâché à chaque lot, ce qui permet aux
    opérations interactives de passer en priorité.
    """
    if not isinstance(liste_action, list) or not liste_action:
        return 0

    has_conversion = _cc_has_col(conn, "conversion")
    has_id_action = _cc_has_col(conn, "ID_Action")
    has_canal = _cc_has_col(conn, "Canal")
    has_action = _cc_has_col(conn, "Action")
    has_creneau = _cc_has_col(conn, "Creneau")

    changed = 0
    last_rid = 0

    while True:
        with heavy_workload("batch"):
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT
                    cc.rowid AS __rid,
                    cc.*,
                    to_jsonb(cl) AS __client_row
                FROM {CLIENTS_CAMPAGNES_TABLE} cc
                LEFT JOIN {CLIENTS_TABLE} cl
                  ON cl.radical_compte = cc.Radical_compte
                WHERE cc.ID_CAMPAGNE = ?
                  AND cc.rowid > ?
                  AND COALESCE(cc.row_status,0) = 0
                  AND COALESCE(cc.conversion, 0) <> 1
                  AND COALESCE(cc.Action,'') IN ('En attente', 'Objectif')
                ORDER BY cc.rowid
                LIMIT ?
                """,
                (id_campagne, int(last_rid), int(BATCH_ROW_CHUNK_SIZE)),
            )

            rows = cur.fetchall()
            if not rows:
                break

            for source_row in rows:
                row = dict(source_row)
                rid = int(row["__rid"])
                last_rid = max(last_rid, rid)
                id_action = _norm_str(row.get("ID_Action"))

                client_row = row.pop("__client_row", None)
                if isinstance(client_row, dict):
                    _inject_client_fields(row, client_row)

                current = find_bloc_by_id(liste_action, id_action)
                if not current:
                    continue

                if is_objective_bloc(current):
                    cur_id = _norm_str(current.get("ID")) or id_action

                    must_update = (
                        (has_id_action and _norm_str(row.get("ID_Action")) != cur_id)
                        or (has_canal and _norm_str(row.get("Canal")) != "Objectif")
                        or (has_action and _norm_str(row.get("Action")) != "Objectif")
                        or (has_creneau and _norm_str(row.get("Creneau")) != "Indifferent")
                    )

                    if must_update:
                        set_parts: List[str] = []
                        params: List[Any] = []

                        if has_id_action:
                            set_parts.append("ID_Action = ?")
                            params.append(cur_id)
                        if has_canal:
                            set_parts.append("Canal = 'Objectif'")
                        if has_action:
                            set_parts.append("Action = 'Objectif'")
                        if has_creneau:
                            set_parts.append("\"Creneau\" = 'Indifferent'")

                        update_sql = (
                            f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET "
                            + ", ".join(set_parts)
                            + " WHERE rowid = ?"
                        )
                        params.append(rid)
                        cur.execute(update_sql, params)
                        changed += int(cur.rowcount or 0)

                        row["ID_Action"] = cur_id
                        row["Canal"] = "Objectif"
                        row["Action"] = "Objectif"
                        if has_creneau:
                            row["Creneau"] = "Indifferent"

                    if has_conversion:
                        branch = objective_branch(current, row)
                        if branch == "Non":
                            finalize_current_sequence(
                                conn,
                                rid,
                                objective_validated=0,
                                objective_id_action=cur_id,
                            )

                        if branch == "Oui":
                            try:
                                conv_val = int(row.get("conversion") or 0)
                            except Exception:
                                conv_val = 0

                            if conv_val != 1:
                                converted_now = mark_converted(
                                    conn,
                                    rid,
                                    objective_id_action=cur_id,
                                )
                                if converted_now:
                                    changed += 1
                                row["conversion"] = 1

                            if int(row.get("conversion") or 0) == 1:
                                continue

                nxt = pick_next_child(liste_action, current, row)

                if not nxt:
                    if has_action and _norm_str(row.get("Action")) != "En attente":
                        cur.execute(
                            f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET Action='En attente' WHERE rowid = ?",
                            (rid,),
                        )
                        changed += int(cur.rowcount or 0)
                    continue

                new_id = _norm_str(nxt.get("ID"))
                if is_objective_bloc(nxt):
                    record_objective_entry(
                        conn,
                        rid,
                        source_id_action=id_action,
                        source_canal=_norm_str(row.get("Canal")),
                    )
                    new_canal = "Objectif"
                    new_action = "Objectif"
                    new_creneau = "Indifferent"
                else:
                    new_canal = _norm_str(nxt.get("Canal"))
                    new_action = _norm_str(nxt.get("Action"))
                    new_creneau = normalize_creneau(nxt.get("Creneau"))

                if not new_id or not new_action:
                    continue

                if has_creneau:
                    cur.execute(
                        f"""
                        UPDATE {CLIENTS_CAMPAGNES_TABLE}
                        SET ID_Action = ?, Canal = ?, Action = ?, "Creneau" = ?
                        WHERE rowid = ?
                        """,
                        (new_id, new_canal, new_action, new_creneau, rid),
                    )
                else:
                    cur.execute(
                        f"""
                        UPDATE {CLIENTS_CAMPAGNES_TABLE}
                        SET ID_Action = ?, Canal = ?, Action = ?
                        WHERE rowid = ?
                        """,
                        (new_id, new_canal, new_action, rid),
                    )
                changed += int(cur.rowcount or 0)

            # Les objets du lot peuvent être libérés et les opérations
            # interactives peuvent prendre le slot avant le lot suivant.
            conn.commit()
            del rows

    return int(changed)

def _update_arriv_eche_for_campaign(
    conn: RuntimeConnection,
    id_campagne: str,
    liste_action: List[Dict[str, Any]],
) -> int:
    """
    Calcule arriv_eche en bulk PostgreSQL.

    La règle métier historique ne dépend ici que de NB_jour_last_action :
    une échéance vaut Oui si une condition enfant sur ce compteur est déjà
    satisfaite ou se trouve à +/- 1 jour. On transforme cette règle en
    prédicats SQL par bloc au lieu de parcourir chaque client Python.
    """
    if not id_campagne or not isinstance(liste_action, list) or not liste_action:
        return 0

    cur = conn.cursor()
    changed = 0

    def _children(parent_id: str) -> List[Dict[str, Any]]:
        parent = find_bloc_by_id(liste_action, parent_id) or {}
        children = parent.get("Fils")
        if isinstance(children, list) and children:
            return [x for x in children if isinstance(x, dict)]
        out: List[Dict[str, Any]] = []
        for b in liste_action:
            if not isinstance(b, dict):
                continue
            parents = b.get("Parents")
            if isinstance(parents, list) and parent_id in {_norm_str(x) for x in parents}:
                out.append(b)
                continue
            legacy = b.get("Bloc_mere") if b.get("Bloc_mere") is not None else b.get("Bloc_mère")
            if _norm_str(legacy) == parent_id:
                out.append(b)
        return out

    days_since_last_action = (
        "CASE WHEN COALESCE(Date_last_action,'') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' "
        "THEN GREATEST(0, CURRENT_DATE - SUBSTRING(Date_last_action FROM 1 FOR 10)::date) "
        "ELSE COALESCE(NB_jour_last_action,0) END"
    )

    def _deadline_predicates(parent_id: str) -> tuple[List[str], List[Any]]:
        predicates: List[str] = []
        params: List[Any] = []
        for child in _children(parent_id):
            conds = child.get("Conditions") or []
            if not isinstance(conds, list):
                conds = []
            cbp = child.get("ConditionsByParent") or {}
            parent_conds = []
            if isinstance(cbp, dict):
                parent_conds = cbp.get(parent_id) or cbp.get(str(parent_id)) or []
            if not isinstance(parent_conds, list):
                parent_conds = []

            for c in list(conds) + list(parent_conds):
                if not isinstance(c, dict):
                    continue
                field = _norm_str(c.get("field") or c.get("Colonne"))
                if _norm_cmp(field) not in (
                    _norm_cmp("NB jours depuis last action"),
                    _norm_cmp("NB_jour_last_action"),
                ):
                    continue
                op = _norm_str(c.get("op") or c.get("Operateur")) or "="
                raw = c.get("value", c.get("Valeur"))
                try:
                    target = float(raw)
                except Exception:
                    continue

                # Condition satisfaite OU distance à la valeur <= 1.
                if op in ("=", "=="):
                    predicates.append(f"ABS(({days_since_last_action})::double precision - ?) <= 1")
                    params.append(target)
                elif op in ("!=", "<>"):
                    # != est vraie partout sauf exactement target, et le cas exact
                    # est malgré tout à distance 0 <= 1 : donc toujours Oui.
                    predicates.append("TRUE")
                elif op in (">", ">="):
                    predicates.append(f"({days_since_last_action})::double precision >= ?")
                    params.append(target - 1.0)
                elif op in ("<", "<="):
                    predicates.append(f"({days_since_last_action})::double precision <= ?")
                    params.append(target + 1.0)
        return predicates, params

    tracked_deadline_blocks: List[str] = []

    for bloc in liste_action:
        if not isinstance(bloc, dict):
            continue
        block_id = _norm_str(bloc.get("ID"))
        if not block_id:
            continue
        predicates, params = _deadline_predicates(block_id)
        if not predicates:
            continue
        tracked_deadline_blocks.append(block_id)
        where_deadline = " OR ".join(f"({p})" for p in predicates)
        # Une seule écriture par ligne réellement changée. L'ancienne logique
        # mettait d'abord toutes les échéances à Non puis remettait les mêmes
        # lignes à Oui à chaque batch, générant inutilement du WAL.
        cur.execute(
            f"""
            WITH desired AS (
                SELECT id,
                       CASE WHEN ({where_deadline}) THEN 'Oui' ELSE 'Non' END AS value
                FROM {CLIENTS_CAMPAGNES_TABLE}
                WHERE ID_CAMPAGNE = ?
                  AND COALESCE(row_status,0) = 0
                  AND COALESCE(conversion,0) <> 1
                  AND ID_Action = ?
            )
            UPDATE {CLIENTS_CAMPAGNES_TABLE} AS cc
            SET arriv_eche = desired.value
            FROM desired
            WHERE cc.id = desired.id
              AND COALESCE(cc.arriv_eche,'') <> desired.value
            """,
            [*params, id_campagne, block_id],
        )
        changed += int(cur.rowcount or 0)

    # Nettoie uniquement les anciens Oui devenus impossibles (bloc sans règle,
    # conversion ou neutralisation). Les Oui encore valides ne sont pas touchés.
    if tracked_deadline_blocks:
        cur.execute(
            f"""
            UPDATE {CLIENTS_CAMPAGNES_TABLE}
            SET arriv_eche = 'Non'
            WHERE ID_CAMPAGNE = ?
              AND COALESCE(arriv_eche,'') = 'Oui'
              AND (
                  COALESCE(row_status,0) <> 0
                  OR COALESCE(conversion,0) = 1
                  OR NOT (ID_Action = ANY(?))
              )
            """,
            (id_campagne, tracked_deadline_blocks),
        )
    else:
        cur.execute(
            f"""
            UPDATE {CLIENTS_CAMPAGNES_TABLE}
            SET arriv_eche = 'Non'
            WHERE ID_CAMPAGNE = ?
              AND COALESCE(arriv_eche,'') = 'Oui'
            """,
            (id_campagne,),
        )
    changed += int(cur.rowcount or 0)

    return int(changed)

def _rebuild_outputs_for_all_en_cours(
    conn: RuntimeConnection,
    campagnes: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Reconstruit les sorties campagne par campagne sans DELETE global.

    Le DELETE global historique pouvait supprimer les sorties qu'une requête
    interactive venait de créer en parallèle. Il forçait aussi une grosse
    reconstruction monolithique. Chaque campagne est désormais isolée et
    passe par un slot batch court.
    """
    ensure_crc_input_table()
    ensure_vers_da_table()
    ensure_vers_cc_table()

    n_crc = 0
    n_da = 0
    n_cc = 0
    n_external_queued = 0
    n_external_pending = 0
    n_external_sent = 0
    n_external_errors = 0

    for campagne in campagnes:
        if _get_campaign_state(campagne) != "En cours":
            continue

        id_campagne = _norm_str(campagne.get("id_campagne"))
        if not id_campagne:
            continue

        type_campagne = (
            _norm_str(campagne.get("type_campagne"))
            or "sans_action_terrain"
        )

        # Les écritures DB massives sont sérialisées avec les autres travaux
        # lourds, mais le slot est libéré avant les appels réseau terrain.
        with heavy_workload("batch"):
            _delete_outputs_for_campagne(id_campagne)
            n_crc += int(
                fill_crc_input_from_clients_campagnes(id_campagne) or 0
            )

            if type_campagne != "avec_action_terrain":
                n_da += int(
                    fill_action_vers_da_from_clients_campagnes(id_campagne) or 0
                )
                n_cc += int(
                    fill_action_vers_cc_from_clients_campagnes(id_campagne) or 0
                )

        # Les sorties Terrain externes sont publiées progressivement par
        # l'Outbound Producer global. Le batch ne préremplit pas une file géante.

    return {
        "crc_input": n_crc,
        "vers_da": n_da,
        "vers_cc": n_cc,
        "external_visit_queued": n_external_queued,
        "external_visit_pending": n_external_pending,
        "external_visit_sent": n_external_sent,
        "external_visit_errors": n_external_errors,
    }


# =========================================================
# Public
# =========================================================
def run_batch_manuel() -> Dict[str, Any]:
    """
    Batch métier principal :
    1. Ruptures de relation.
    2. Mise à jour temporelle des campagnes.
    3. Recalcul des compteurs.
    4. Progression En attente / Objectif.
    5. Synchronisation incrémentale insert-only des cibles.
    6. Calcul des échéances.
    7. Traitement mail.
    8. Reconstruction des outputs.
    """
    ensure_clients_campagnes()

    campagnes = list_all_campagnes()
    actives = _list_active_campaigns(campagnes)

    out: Dict[str, Any] = {
        "statut_actuel_updated": 0,
        "rupture_canceled": 0,
        "campagnes_status": {
            "to_en_cours": 0,
            "to_terminee": 0,
            "invalid_dates": 0,
        },
        "nb_jour_last_action_updated": 0,
        "nb_jour_debut_campagne_updated": 0,
        "arriv_eche_updated": 0,
        "en_attente_advanced": 0,
        "new_clients_added_from_cibles": 0,
        "new_cible_members": 0,
        "target_sync": {
            "campaigns_processed": 0,
            "campaigns_succeeded": 0,
            "campaigns_failed": 0,
            "changes_processed": 0,
            "bootstrap_campaigns": 0,
            "pruned_changes": 0,
            "details": [],
        },
        "mails_processed": None,
        "outputs_rebuilt": {
            "crc_input": 0,
            "vers_da": 0,
            "vers_cc": 0,
            "external_visit_queued": 0,
            "external_visit_pending": 0,
            "external_visit_sent": 0,
            "external_visit_errors": 0,
        },
    }

    conn = _connect()
    try:
        # 1) Mise à jour temporelle des campagnes. La détection des ruptures
        # est désormais couplée aux deltas de targeting : plus de scan complet
        # de chaque campagne à chaque batch.
        out["campagnes_status"] = _update_campaigns_status_from_dates(
            campagnes
        )

        campagnes = list_all_campagnes()
        actives = _list_active_campaigns(campagnes)

        # 2) Compteurs journaliers virtualisés (aucun UPDATE massif).
        out["nb_jour_last_action_updated"] = _recompute_nb_jour_last_action(
            conn
        )
        out["nb_jour_debut_campagne_updated"] = (
            _recompute_nb_jour_debut_campagne(conn)
        )

        conn.commit()

        # 3) Progression En attente / Objectif.
        for campagne in actives:
            id_campagne = _norm_str(campagne.get("id_campagne"))
            id_modele = _norm_str(campagne.get("id_modele"))
            if not id_campagne or not id_modele:
                continue

            liste_action = _load_modele_meta(conn, id_modele)
            out["en_attente_advanced"] += _advance_en_attente_rows(
                conn,
                id_campagne,
                liste_action,
            )

        conn.commit()

        # 4) Synchronisation incrémentale des cibles + ruptures.
        for campagne in actives:
            id_campagne = _norm_str(campagne.get("id_campagne"))
            if not id_campagne:
                continue

            out["target_sync"]["campaigns_processed"] += 1

            try:
                with heavy_workload("batch"):
                    result = sync_target_changes_for_campaign(
                        id_campagne,
                        bootstrap_if_needed=True,
                        wait_for_lock=True,
                    )

                out["rupture_canceled"] += int(result.get("rupture_canceled") or 0)
                detail = {
                    "id_campagne": id_campagne,
                    "etat": _get_campaign_state(campagne),
                    "ok": bool(result.get("ok")),
                    "bootstrap": bool(result.get("bootstrap")),
                    "changes_processed": int(result.get("changes_processed") or 0),
                    "watermark": int(result.get("watermark") or 0),
                    "new_cible_members": int(
                        result.get("new_cible_members") or 0
                    ),
                    "new_clients_campagne": int(
                        result.get("new_clients_campagne") or 0
                    ),
                }

                if result.get("ok"):
                    out["target_sync"]["campaigns_succeeded"] += 1
                    out["target_sync"]["changes_processed"] += detail["changes_processed"]
                    if detail["bootstrap"]:
                        out["target_sync"]["bootstrap_campaigns"] += 1
                    out["new_cible_members"] += detail["new_cible_members"]
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

        # Les changements dont toutes les campagnes suivies ont dépassé le
        # watermark peuvent être purgés. La table reste donc bornée au volume
        # réellement en retard, pas à l'historique complet des modifications.
        try:
            out["target_sync"]["pruned_changes"] = int(prune_processed_changes() or 0)
        except Exception as exc:
            out["target_sync"]["prune_error"] = str(exc)

        # 6) Calcul des échéances.
        for campagne in actives:
            id_campagne = _norm_str(campagne.get("id_campagne"))
            id_modele = _norm_str(campagne.get("id_modele"))
            if not id_campagne or not id_modele:
                continue

            liste_action = _load_modele_meta(conn, id_modele)
            out["arriv_eche_updated"] += _update_arriv_eche_for_campaign(
                conn,
                id_campagne,
                liste_action,
            )

        conn.commit()

        # 7) Mail/Terrain sont pris en charge par l'Outbound Engine. Le batch
        # ne fait plus d'I/O réseau et libère rapidement ses ressources.
        out["mails_processed"] = {"delegated_to_outbound": True}

        # 8) Reconstruction des outputs internes.
        out["outputs_rebuilt"] = _rebuild_outputs_for_all_en_cours(
            conn,
            campagnes,
        )

    finally:
        conn.close()

    return out
