# app/scripts/batch_manuel.py
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from app.storage.db import DB_PATH
from app.storage.campagnes_store_sqlite import list_all_campagnes, update_etat
from app.storage.clients_campagnes_store_sqlite import (
    ensure_table as ensure_clients_campagnes,
    set_clients_etat_for_campagne,
)

# outputs (phase 1)
from app.storage.crc_input_store_sqlite import ensure_crc_input_table, clear_crc_input, fill_crc_input_from_clients_campagnes
from app.storage.action_vers_da_store_sqlite import ensure_vers_da_table, fill_action_vers_da_from_clients_campagnes
from app.storage.action_vers_cc_store_sqlite import ensure_vers_cc_table, fill_action_vers_cc_from_clients_campagnes

from app.engine.traitement_mail_engine import run_mail_meta_loop
from app.domain.workflow_nav import objective_reached, find_bloc_by_id, pick_next_child, arrive_echeance


CLIENTS_CAMPAGNES_TABLE = "clients_campagnes"
CAMPAGNES_TABLE = "campagnes"
MODELES_TABLE = "modeles"
CLIENTS_TABLE = "clients"


# =========================================================
# Helpers
# =========================================================
def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _norm_str(x: Any) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    return "" if s.lower() == "none" else s


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


def _clients_columns(conn: sqlite3.Connection) -> List[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({CLIENTS_TABLE})")
    return [r[1] for r in cur.fetchall()]


def _resolve_clients_col(conn: sqlite3.Connection, requested_col: str) -> Optional[str]:
    """
    Résout une colonne de la table clients de manière robuste:
    - match exact
    - sinon match insensible à la casse/accents/espaces via _norm_cmp
    Retourne le NOM réel de la colonne dans la DB (à utiliser dans le SQL).
    """
    req = _norm_str(requested_col)
    if not req:
        return None

    cols = _clients_columns(conn)
    # 1) exact
    if req in cols:
        return req

    # 2) normalized compare
    req_n = _norm_cmp(req)
    for c in cols:
        if _norm_cmp(c) == req_n:
            return c

    return None


def _modeles_id_col(conn: sqlite3.Connection) -> str:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({MODELES_TABLE})")
    cols = [r[1] for r in cur.fetchall()]
    if "id_modele" in cols:
        return "id_modele"
    if "ID_MODELE" in cols:
        return "ID_MODELE"
    return "id_modele"



def _load_client_row_by_radical(conn: sqlite3.Connection, radical_compte: str) -> Dict[str, Any]:
    """Charge la ligne clients.* pour un radical_compte.
    Retourne un dict {col: value}. Si introuvable -> {}.

    Note: on résout le nom réel de la colonne 'radical_compte' pour éviter les soucis de casse.
    """
    rc = _norm_str(radical_compte)
    if not rc:
        return {}

    conn.row_factory = sqlite3.Row
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
    """Enrichit une ligne clients_campagnes avec les champs clients.* pour l'évaluation des conditions.

    - conserve les clés existantes
    - ajoute col -> value
    - ajoute client.col -> value (format utilisé par l'UI pour les conditions DB)

    Robustesse supplémentaire (sans casser l'existant):
    - ajoute aussi des alias de clés "compactées" (sans espaces / sauts de ligne)
      pour couvrir des champs qui auraient été sauvegardés/affichés avec wrapping.
      Ex:
        'client.nb_retrai\nt_gab' ou 'client.nb_retrait gab' => alias vers 'client.nb_retrait_gab'
    """
    if not isinstance(row_clients_campagnes, dict) or not isinstance(client_row, dict):
        return row_clients_campagnes

    def _add_key(key: str, value: Any) -> None:
        if key and key not in row_clients_campagnes:
            row_clients_campagnes[key] = value

        # alias compact (supprime espaces + \n + \r + \t)
        key_compact = re.sub(r"\s+", "", key)
        if key_compact and key_compact not in row_clients_campagnes:
            row_clients_campagnes[key_compact] = value

    for k, v in client_row.items():
        # ne pas écraser les champs métier déjà présents dans clients_campagnes
        if k not in row_clients_campagnes:
            row_clients_campagnes[k] = v

        _add_key(f"client.{k}", v)
        _add_key(str(k), v)

    return row_clients_campagnes
    for k, v in client_row.items():
        # ne pas écraser les champs métier déjà présents dans clients_campagnes
        if k not in row_clients_campagnes:
            row_clients_campagnes[k] = v
        key2 = f"client.{k}"
        if key2 not in row_clients_campagnes:
            row_clients_campagnes[key2] = v
    return row_clients_campagnes


# =========================================================
# Batch steps (ordre imposé)
# =========================================================
def _list_active_campaigns(campagnes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for c in campagnes:
        etat = _norm_str(c.get("etat") or c.get("etat_campagne"))
        if etat in ("En cours", "Planifiée", "En pause"):
            out.append(c)
    return out


def _load_modele_meta(conn: sqlite3.Connection, id_modele: str) -> Tuple[str, str, List[Dict[str, Any]]]:
    id_col = _modeles_id_col(conn)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT variable_cible, objectif, liste_action FROM {MODELES_TABLE} WHERE {id_col} = ?", (id_modele,))
    r = cur.fetchone()
    if not r:
        return "", "", []
    variable_cible = _norm_str(r["variable_cible"])
    objectif = _norm_str(r["objectif"])
    raw = r["liste_action"]
    if isinstance(raw, list):
        liste_action = raw
    else:
        liste_action = _safe_json_loads(_norm_str(raw), [])
        if not isinstance(liste_action, list):
            liste_action = []
    return variable_cible, objectif, liste_action


def _update_statut_actuel_from_clients(conn: sqlite3.Connection, id_campagne: str, variable_cible: str) -> int:
    """
    Met à jour clients_campagnes.statut_actuel depuis clients.<variable_cible>.
    Fix: résolution de colonne clients en case-insensitive (évite les var = 'statut_client' vs 'STATUT_CLIENT').
    """
    var = _norm_str(variable_cible)
    if not var:
        return 0

    resolved_col = _resolve_clients_col(conn, var)
    if not resolved_col:
        return 0

    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE {CLIENTS_CAMPAGNES_TABLE}
        SET statut_actuel = (
            SELECT COALESCE(cl."{resolved_col}", '')
            FROM {CLIENTS_TABLE} cl
            WHERE cl.radical_compte = {CLIENTS_CAMPAGNES_TABLE}.Radical_compte
        )
        WHERE ID_CAMPAGNE = ?
          AND COALESCE(Etat_campagne,'') IN ('En cours','Planifiée', 'En pause')
        """,
        (id_campagne,),
    )
    return int(cur.rowcount or 0)


def _close_if_objective_reached(conn: sqlite3.Connection, id_campagne: str, objectif: str) -> int:
    """
    On ferme (Closed) toutes les lignes dont statut_actuel atteint l'objectif du modèle.
    Robustesse: comparaison normalisée via objective_reached (python rowid).
    """
    objectif = _norm_str(objectif)
    if not objectif:
        return 0

    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT rowid as __rid, statut_actuel, Action
        FROM {CLIENTS_CAMPAGNES_TABLE}
        WHERE ID_CAMPAGNE=?
          AND COALESCE(Etat_campagne,'') IN ('En cours','Planifiée', 'En pause')
          AND COALESCE(Action,'') <> 'Closed'
        """,
        (id_campagne,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    n = 0
    for r in rows:
        rid = int(r["__rid"])
        if objective_reached(r.get("statut_actuel"), objectif):
            cur.execute(
                f"UPDATE {CLIENTS_CAMPAGNES_TABLE} SET Action='Closed', Canal='Closed' WHERE rowid=?",
                (rid,),
            )
            n += int(cur.rowcount or 0)
    return n


def _cancel_if_rupture_relation(conn: sqlite3.Connection, id_campagne: str) -> int:
    cols = set(_clients_columns(conn))
    if "STATUT_CLIENT" not in cols and "statut_client" not in cols:
        return 0

    statut_col = "STATUT_CLIENT" if "STATUT_CLIENT" in cols else "statut_client"

    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE {CLIENTS_CAMPAGNES_TABLE}
        SET statut_actuel = 'canceled'
        WHERE ID_CAMPAGNE = ?
          AND COALESCE(Etat_campagne,'') IN ('En cours','Planifiée', 'En pause')
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


def _update_campaigns_status_from_dates(campagnes: List[Dict[str, Any]]) -> Dict[str, int]:
    today = date.today()
    counts = {"to_en_cours": 0, "to_terminee": 0}

    for c in campagnes:
        id_c = _norm_str(c.get("id_campagne"))
        etat = _norm_str(c.get("etat") or c.get("etat_campagne"))
        d0 = _parse_iso_date(c.get("date_debut"))
        d1 = _parse_iso_date(c.get("date_fin"))

        if not id_c or etat == "Annulée" or not d0 or not d1:
            continue

        if etat == "En pause":
            continue

        if etat == "Planifiée" and d0 <= today <= d1:
            update_etat(id_c, "En cours")
            set_clients_etat_for_campagne(id_c, "En cours")
            counts["to_en_cours"] += 1

        if etat == "En cours" and d1 < today:
            update_etat(id_c, "Terminée")
            set_clients_etat_for_campagne(id_c, "Terminée")
            counts["to_terminee"] += 1

    return counts


def _recompute_nb_jour_last_action(conn: sqlite3.Connection) -> int:
    today_iso = date.today().isoformat()
    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE {CLIENTS_CAMPAGNES_TABLE}
        SET NB_jour_last_action = CASE
            WHEN COALESCE(Date_last_action,'') = '' THEN 0
            ELSE CAST((julianday(?) - julianday(substr(Date_last_action,1,10))) AS INTEGER)
        END
        WHERE COALESCE(Etat_campagne,'') IN ('En cours','Planifiée', 'En pause')
        """,
        (today_iso,),
    )
    return int(cur.rowcount or 0)


def _advance_en_attente_rows(conn: sqlite3.Connection, id_campagne: str, liste_action: List[Dict[str, Any]]) -> int:
    if not isinstance(liste_action, list) or len(liste_action) == 0:
        return 0

    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        f"""
        SELECT rowid as __rid, *
        FROM {CLIENTS_CAMPAGNES_TABLE}
        WHERE ID_CAMPAGNE = ?
          AND COALESCE(Etat_campagne,'') IN ('En cours','Planifiée', 'En pause')
          AND COALESCE(Action,'') = 'En attente'
        """,
        (id_campagne,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    changed = 0

    # Cache clients.* par radical_compte (évite N requêtes identiques)
    _client_cache: Dict[str, Dict[str, Any]] = {}

    for r in rows:
        rid = int(r["__rid"])
        id_action = _norm_str(r.get("ID_Action"))

        # Enrichissement: ajouter les champs de la table clients pour permettre
        # les conditions du type client.nb_transaction <= 500
        rc = _norm_str(r.get("Radical_compte") or r.get("radical_compte"))
        if rc:
            if rc not in _client_cache:
                _client_cache[rc] = _load_client_row_by_radical(conn, rc)
            _inject_client_fields(r, _client_cache.get(rc, {}))

        current = find_bloc_by_id(liste_action, id_action)
        if not current:
            continue

        nxt = pick_next_child(liste_action, current, r)
        if not nxt:
            continue

        new_id = _norm_str(nxt.get("ID"))
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
    conn: sqlite3.Connection,
    id_campagne: str,
    liste_action: List[Dict[str, Any]],
) -> int:
    """
    Met à jour clients_campagnes.arriv_eche ('Oui'/'Non') pour une campagne.
    Règles (alignées sur les règles déjà utilisées ailleurs):
      - seulement pour Etat_campagne in ('En cours','Planifiée','En pause')
      - si Action == 'Closed' => arriv_eche = 'Non'
      - sinon on calcule via arrive_echeance(liste_action, bloc_courant, row)
    Retourne le nombre de lignes effectivement modifiées.
    """
    if not id_campagne or not isinstance(liste_action, list) or len(liste_action) == 0:
        return 0

    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # NB: arriv_eche doit exister (géré par ensure_table du store)
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

def _rebuild_outputs_for_all_en_cours(conn: sqlite3.Connection, campagnes: List[Dict[str, Any]]) -> Dict[str, int]:
    ensure_crc_input_table()
    ensure_vers_da_table()
    ensure_vers_cc_table()

    clear_crc_input()
    cur = conn.cursor()
    cur.execute("DELETE FROM vers_da")
    cur.execute("DELETE FROM vers_cc")
    conn.commit()

    n_crc = 0
    n_da = 0
    n_cc = 0

    for c in campagnes:
        etat = _norm_str(c.get("etat") or c.get("etat_campagne"))
        if etat != "En cours":
            continue
        id_c = _norm_str(c.get("id_campagne"))
        if not id_c:
            continue

        n_crc += int(fill_crc_input_from_clients_campagnes(id_c) or 0)
        n_da += int(fill_action_vers_da_from_clients_campagnes(id_c) or 0)
        n_cc += int(fill_action_vers_cc_from_clients_campagnes(id_c) or 0)

    return {"crc_input": n_crc, "vers_da": n_da, "vers_cc": n_cc}

def sync_new_clients_from_cible_insert_only(
    conn: sqlite3.Connection,
    *,
    id_campagne: str,
    id_cible: str,
    # valeurs initiales workflow (à fournir depuis ton modèle)
    id_action_initiale: str,
    canal_initial: str,
    action_initial: str,
) -> int:
    """
    INSERT ONLY:
    - charge la requête SQL de la cible (table cibles)
    - exécute la requête pour obtenir les radical_compte éligibles
    - insère dans clients_campagnes uniquement ceux qui n'y sont pas déjà pour la campagne

    Ne supprime jamais rien.
    Retourne le nombre de nouveaux clients ajoutés.
    """

    id_campagne = _norm_str(id_campagne)
    id_cible = _norm_str(id_cible)
    if not id_campagne or not id_cible:
        return 0

    # -------------------------
    # 1) Lire le SQL de la cible
    # -------------------------
    CIBLES_TABLE = "cibles"

    def _table_cols(table: str) -> List[str]:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        return [r[1] for r in cur.fetchall()]

    def _resolve_id_col(table: str, candidates: List[str]) -> Optional[str]:
        cols = _table_cols(table)
        for c in candidates:
            if c in cols:
                return c
        # fallback normalized
        for c in cols:
            for cand in candidates:
                if _norm_cmp(c) == _norm_cmp(cand):
                    return c
        return None

    # colonnes possibles pour l'ID de cible
    id_col = _resolve_id_col(CIBLES_TABLE, ["id_cible", "ID_CIBLE", "Id_cible"])
    if not id_col:
        return 0

    # colonnes possibles pour le SQL de la cible
    sql_col_candidates = [
        "sql_query", "SQL_QUERY", "requete_sql", "REQUETE_SQL",
        "filtre_sql", "FILTRE_SQL", "query", "QUERY", "sql", "SQL"
    ]
    sql_col = None
    cols_cibles = _table_cols(CIBLES_TABLE)
    for cand in sql_col_candidates:
        if cand in cols_cibles:
            sql_col = cand
            break
    if not sql_col:
        # fallback normalized
        for c in cols_cibles:
            if _norm_cmp(c) in {_norm_cmp(x) for x in sql_col_candidates}:
                sql_col = c
                break
    if not sql_col:
        return 0

    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT "{sql_col}" as q FROM {CIBLES_TABLE} WHERE "{id_col}" = ? LIMIT 1', (id_cible,))
    except Exception:
        return 0

    r = cur.fetchone()
    if not r:
        return 0

    cible_sql = _norm_str(r["q"])
    if not cible_sql:
        return 0

    # -------------------------
    # 2) Exécuter la requête cible pour obtenir les radical_compte
    # -------------------------
    # On enveloppe la requête cible pour extraire proprement la colonne radical_compte
    # (on résout le nom réel dans la table clients)
    rc_col_clients = _resolve_clients_col(conn, "radical_compte") or "radical_compte"

    # Wrapper safe: on veut une colonne "Radical_compte" en sortie
    wrapped = f'SELECT TRIM(CAST(t."{rc_col_clients}" AS TEXT)) as Radical_compte FROM ({cible_sql}) t'

    try:
        cur.execute(wrapped)
        radicals_rows = cur.fetchall()
    except Exception:
        # Si le wrapper échoue (requête cible non compatible), on tente brut et on lit la colonne radical
        try:
            cur.execute(cible_sql)
            radicals_rows = cur.fetchall()
        except Exception:
            return 0

    radicals: List[str] = []
    # radicals_rows peut être list[Row] ou list[tuple] selon row_factory
    for row in radicals_rows:
        try:
            # Row dict-like
            val = row["Radical_compte"] if "Radical_compte" in row.keys() else row[0]
        except Exception:
            try:
                val = row[0]
            except Exception:
                val = None
        rc = _norm_str(val)
        if rc:
            radicals.append(rc)

    if not radicals:
        return 0

    # unique stable
    radicals = list(dict.fromkeys(radicals))

    # -------------------------
    # 3) Exclure ceux déjà en clients_campagnes (pour cette campagne)
    # -------------------------
    cur.execute(
        f"SELECT Radical_compte FROM {CLIENTS_CAMPAGNES_TABLE} WHERE ID_CAMPAGNE = ?",
        (id_campagne,),
    )
    existing = { _norm_str(x[0]) for x in cur.fetchall() if _norm_str(x[0]) }

    to_add = [rc for rc in radicals if rc not in existing]
    if not to_add:
        return 0

    # -------------------------
    # 4) INSERT ONLY (tolérant au schéma)
    # -------------------------
    cols_cc = set(_table_cols(CLIENTS_CAMPAGNES_TABLE))

    today_iso = date.today().isoformat()
    now_iso = _now_iso()

    def _build_row(rc: str) -> Dict[str, Any]:
        row: Dict[str, Any] = {}

        if "ID_CAMPAGNE" in cols_cc:
            row["ID_CAMPAGNE"] = id_campagne
        if "Radical_compte" in cols_cc:
            row["Radical_compte"] = rc

        # Init workflow
        if "ID_Action" in cols_cc:
            row["ID_Action"] = _norm_str(id_action_initiale)
        if "Canal" in cols_cc:
            row["Canal"] = _norm_str(canal_initial)
        if "Action" in cols_cc:
            row["Action"] = _norm_str(action_initial)

        # Etat (si présent)
        if "Etat_campagne" in cols_cc:
            # à la sync, on colle au statut de la campagne (souvent En cours / Planifiée / En pause)
            # tu peux remplacer par la valeur que tu veux au moment de l'appel
            row["Etat_campagne"] = "En cours"

        # Dates / KPI
        if "Date_affectation" in cols_cc:
            row["Date_affectation"] = today_iso
        if "Date_last_action" in cols_cc:
            row["Date_last_action"] = ""  # ou None
        if "NB_jour_last_action" in cols_cc:
            row["NB_jour_last_action"] = 0
        if "Resultat_last_action" in cols_cc:
            row["Resultat_last_action"] = ""
        if "arriv_eche" in cols_cc:
            row["arriv_eche"] = "Non"
        if "statut_actuel" in cols_cc:
            row["statut_actuel"] = ""

        # si tu as un champ timestamp générique
        if "updated_at" in cols_cc:
            row["updated_at"] = now_iso
        if "created_at" in cols_cc and "created_at" not in row:
            row["created_at"] = now_iso

        return row

    rows = [_build_row(rc) for rc in to_add]

    # construit INSERT sur colonnes existantes
    insert_cols = list(rows[0].keys())
    placeholders = ",".join(["?"] * len(insert_cols))
    cols_sql = ",".join([f'"{c}"' for c in insert_cols])

    sql_ins = f'INSERT INTO {CLIENTS_CAMPAGNES_TABLE} ({cols_sql}) VALUES ({placeholders})'
    data = [tuple(r.get(c) for c in insert_cols) for r in rows]

    cur.executemany(sql_ins, data)
    return len(rows)

# =========================================================
# Public (lié au bouton refresh)
# =========================================================
def run_batch_manuel() -> Dict[str, Any]:
    """
    Ordre EXACT demandé + ajout:
    - close objectif (Closed)
    - traitement mails après MAJ/advance et avant rebuild outputs
    - NEW: sync nouveaux clients depuis cible (INSERT ONLY) entre 5 et 5bis
    """
    ensure_clients_campagnes()

    campagnes = list_all_campagnes()
    actives = _list_active_campaigns(campagnes)

    out: Dict[str, Any] = {
        "statut_actuel_updated": 0,
        "rupture_canceled": 0,
        "campagnes_status": {"to_en_cours": 0, "to_terminee": 0},
        "nb_jour_last_action_updated": 0,
        "arriv_eche_updated": 0,
        "en_attente_advanced": 0,
        "closed_objectif": 0,
        "new_clients_added_from_cibles": 0,  # NEW KPI
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

            variable_cible, objectif, _liste_action = _load_modele_meta(conn, id_modele)
            out["statut_actuel_updated"] += _update_statut_actuel_from_clients(conn, id_c, variable_cible)

            # 2) rupture relation -> canceled
            out["rupture_canceled"] += _cancel_if_rupture_relation(conn, id_c)

            # NEW: close objectif
            out["closed_objectif"] += _close_if_objective_reached(conn, id_c, objectif)

        conn.commit()

        # 3) update campagnes statuses
        out["campagnes_status"] = _update_campaigns_status_from_dates(campagnes)

        campagnes = list_all_campagnes()
        actives = _list_active_campaigns(campagnes)

        # 4) recompute NB_jour_last_action
        out["nb_jour_last_action_updated"] = _recompute_nb_jour_last_action(conn)
        conn.commit()

        # 5) advance En attente
        for c in actives:
            id_c = _norm_str(c.get("id_campagne"))
            id_modele = _norm_str(c.get("id_modele"))
            if not id_c or not id_modele:
                continue
            _var, objectif, liste_action = _load_modele_meta(conn, id_modele)

            # re-close objectif au cas où NB_jour ou update a modifié des conditions externes
            out["closed_objectif"] += _close_if_objective_reached(conn, id_c, objectif)

            out["en_attente_advanced"] += _advance_en_attente_rows(conn, id_c, liste_action)

        conn.commit()

        # 5.5) NEW: sync nouveaux clients depuis cibles (INSERT ONLY) - par campagne active
        for c in actives:
            id_c = _norm_str(c.get("id_campagne"))
            id_cible = _norm_str(c.get("id_cible") or c.get("ID_CIBLE"))
            if not id_c or not id_cible:
                continue

            out["new_clients_added_from_cibles"] += sync_new_clients_from_cible_insert_only(
                conn,
                id_campagne=id_c,
                id_cible=id_cible,
                id_action_initiale="2",
                canal_initial="Appel",
                action_initial="Appeler",
            )

        conn.commit()

        # 5bis) update arriv_eche (après recompute NB_jour_last_action et advance)
        for c in actives:
            id_c = _norm_str(c.get("id_campagne"))
            id_modele = _norm_str(c.get("id_modele"))
            if not id_c or not id_modele:
                continue
            _var2, _obj2, liste_action2 = _load_modele_meta(conn, id_modele)
            out["arriv_eche_updated"] += _update_arriv_eche_for_campaign(conn, id_c, liste_action2)

        conn.commit()

        # NEW: traiter mails (après mises à jour/advance)
        out["mails_processed"] = run_mail_meta_loop(max_passes=10, limit_rows_per_pass=5000)

        # 6) rebuild outputs
        out["outputs_rebuilt"] = _rebuild_outputs_for_all_en_cours(conn, campagnes)

    finally:
        conn.close()

    return out
