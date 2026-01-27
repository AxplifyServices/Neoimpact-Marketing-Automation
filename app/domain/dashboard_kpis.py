from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd

from app.storage.db import DB_PATH

# =========================================================
# Constantes / tables
# =========================================================
CLIENTS_TABLE = "clients_campagnes"
CAMPAGNES_TABLE = "campagnes"
CLIENTS_DIM_TABLE = "clients"
MODELES_TABLE = "modeles"

# États dashboard (DB truth)
# NB: "En pause" n'existe peut-être pas dans ta DB actuelle, mais on le supporte si ça arrive plus tard.
ALLOWED_CAMPAGNE_ETATS = ("Terminée", "En cours", "En pause")

CHANNEL_COLS = [
    ("Appel", "NB_appel"),
    ("Mail", "NB_mail"),
    ("SMS", "NB_sms"),
    ("Message", "NB_message"),
]


# =========================================================
# Helpers
# =========================================================
def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _norm_str(x: object) -> str:
    return "" if x is None else str(x).strip()


def _normalize_action(x: object) -> str:
    return _norm_str(x).lower()


def _to_date_series(s: pd.Series) -> pd.Series:
    dt = pd.to_datetime(s, errors="coerce")
    return dt.dt.date


def _safe_json_loads(x: object, default: Any) -> Any:
    if x is None:
        return default
    if isinstance(x, (dict, list)):
        return x
    try:
        s = str(x).strip()
        return json.loads(s) if s else default
    except Exception:
        return default


# =========================================================
# Filters model
# =========================================================
@dataclass
class DashboardFilters:
    campagne_ids: Optional[List[str]] = None
    etats_campagne: Optional[List[str]] = None  # "Terminée", "En cours", "En pause"
    date_min: Optional[date] = None
    date_max: Optional[date] = None


# =========================================================
# Dynamic filters (campagnes <-> états)
# =========================================================
def list_campagnes_df() -> pd.DataFrame:
    conn = _connect()
    try:
        return pd.read_sql_query(f"SELECT * FROM {CAMPAGNES_TABLE}", conn)
    finally:
        conn.close()


def get_dynamic_filter_options(
    selected_campagne_ids: Optional[List[str]] = None,
    selected_etats: Optional[List[str]] = None,
) -> Dict[str, List[Dict[str, str]]]:
    """
    Filtres dynamiques bidirectionnels.
    - Exclut Annulée.
    - Ne propose que Terminée/En cours/En pause (si existe).
    """
    dfc = list_campagnes_df()
    if dfc.empty:
        return {"etats": [], "campagnes": []}

    dfc["etat_campagne"] = dfc["etat_campagne"].astype(str).str.strip()
    dfc["id_campagne"] = dfc["id_campagne"].astype(str).str.strip()
    dfc["nom_campagne"] = dfc.get("nom_campagne", "").astype(str).str.strip()

    # base: exclude cancelled
    dfc = dfc[dfc["etat_campagne"] != "Annulée"].copy()

    # restrict to allowed
    dfc = dfc[dfc["etat_campagne"].isin(list(ALLOWED_CAMPAGNE_ETATS))].copy()

    # If etats selected => filter campaigns
    if selected_etats:
        sel = [str(x).strip() for x in selected_etats if str(x).strip()]
        if sel:
            dfc = dfc[dfc["etat_campagne"].isin(sel)].copy()

    # If campaigns selected => filter etats
    if selected_campagne_ids:
        selc = [str(x).strip() for x in selected_campagne_ids if str(x).strip()]
        if selc:
            dfc = dfc[dfc["id_campagne"].isin(selc)].copy()

    etats = sorted(dfc["etat_campagne"].dropna().unique().tolist())
    etats_out = [{"value": e, "label": e} for e in etats]

    campagnes = []
    for _, r in dfc.sort_values(["etat_campagne", "nom_campagne", "id_campagne"]).iterrows():
        cid = _norm_str(r.get("id_campagne"))
        nom = _norm_str(r.get("nom_campagne"))
        etat = _norm_str(r.get("etat_campagne"))
        label = f"{nom} — {cid} ({etat})" if nom else f"{cid} ({etat})"
        campagnes.append({"id": cid, "label": label, "etat": etat, "nom": nom})

    return {"etats": etats_out, "campagnes": campagnes}


# =========================================================
# Data access
# =========================================================
def load_clients_campagnes_df(filters: DashboardFilters) -> pd.DataFrame:
    """
    - Exclut Annulée
    - Restrict Etat_campagne à Terminée/En cours/En pause
    - Filtre campagne_ids / etats_campagne si fournis
    - Date_min/max filtrent sur Date_last_action
    """
    where = ["COALESCE(Etat_campagne,'') <> 'Annulée'"]
    params: List[object] = []

    where.append("COALESCE(Etat_campagne,'') IN ('Terminée','En cours','En pause')")

    if filters.campagne_ids:
        placeholders = ",".join(["?"] * len(filters.campagne_ids))
        where.append(f"ID_CAMPAGNE IN ({placeholders})")
        params.extend([str(x).strip() for x in filters.campagne_ids])

    if filters.etats_campagne:
        placeholders = ",".join(["?"] * len(filters.etats_campagne))
        where.append(f"Etat_campagne IN ({placeholders})")
        params.extend([str(x).strip() for x in filters.etats_campagne])

    sql = f"SELECT * FROM {CLIENTS_TABLE}"
    if where:
        sql += " WHERE " + " AND ".join(where)

    conn = _connect()
    try:
        df = pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()

    if df.empty:
        return df

    # normalisations
    df["_action_norm"] = df.get("Action", "").apply(_normalize_action)
    df["_is_closed"] = df["_action_norm"].eq("closed")

    df["ID_Action"] = df.get("ID_Action", "").astype(str).str.strip()
    df["Canal"] = df.get("Canal", "").astype(str).str.strip()
    df["ID_CAMPAGNE"] = df.get("ID_CAMPAGNE", "").astype(str).str.strip()

    df["_has_last_action"] = df.get("Date_last_action", "").astype(str).str.strip().ne("")
    df["_date_last_action"] = _to_date_series(df.get("Date_last_action", pd.Series([None] * len(df))))

    # Règle: ID_Action == 1 => aucun traitement (même si date existe)
    df["_is_treated"] = df["_has_last_action"] & df["ID_Action"].ne("1")

    # dates filter
    if filters.date_min is not None:
        df = df[df["_date_last_action"].notna() & (df["_date_last_action"] >= filters.date_min)]
    if filters.date_max is not None:
        df = df[df["_date_last_action"].notna() & (df["_date_last_action"] <= filters.date_max)]

    for _, col in CHANNEL_COLS:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    return df


def load_clients_dim_regions() -> pd.DataFrame:
    """
    Retourne un DF avec:
      - radical_compte
      - Region (normalisée)
    Détecte automatiquement la colonne région si elle n'est pas exactement 'Region'.
    """
    conn = _connect()
    try:
        df = pd.read_sql_query(f"SELECT * FROM {CLIENTS_DIM_TABLE}", conn)
    finally:
        conn.close()

    if df.empty:
        return pd.DataFrame(columns=["radical_compte", "Region"])

    cols = list(df.columns)

    # colonne radical
    radical_col = None
    for cand in ["radical_compte", "Radical_compte", "RADICAL_COMPTE", "radical"]:
        if cand in cols:
            radical_col = cand
            break
    if radical_col is None:
        for c in cols:
            if "radical" in c.lower():
                radical_col = c
                break
    if radical_col is None:
        return pd.DataFrame(columns=["radical_compte", "Region"])

    # colonne région (auto)
    region_col = None
    preferred = ["Region", "REGION", "region", "Région", "REGION_CLIENT", "Region_client"]
    for cand in preferred:
        if cand in cols:
            region_col = cand
            break
    if region_col is None:
        for c in cols:
            cl = c.lower()
            if "region" in cl or "région" in cl:
                region_col = c
                break
    if region_col is None:
        return pd.DataFrame(columns=["radical_compte", "Region"])

    out = df[[radical_col, region_col]].copy()
    out.columns = ["radical_compte", "Region"]
    out["radical_compte"] = out["radical_compte"].astype(str).str.strip()
    out["Region"] = out["Region"].astype(str).str.strip().replace({"": "Inconnue"}).fillna("Inconnue")
    return out


# =========================================================
# KPI calculations
# =========================================================
def compute_kpis_compact(df: pd.DataFrame) -> Dict[str, Any]:
    if df is None or df.empty:
        return {
            "transmis": 0,
            "contactes_total": 0,
            "closing_total": 0,
            "traitements_total": 0,
            "taux_contact_total": 0.0,
            "taux_closing_sur_affectes": 0.0,
            "taux_closing_sur_traitements_total": 0.0,
        }

    transmis = int(len(df))
    contactes_total = int(df["_is_treated"].sum())
    closing_total = int(df["_is_closed"].sum())
    traitements_total = int(sum(df[col].sum() for _, col in CHANNEL_COLS))

    return {
        "transmis": transmis,
        "contactes_total": contactes_total,
        "closing_total": closing_total,
        "traitements_total": traitements_total,
        "taux_contact_total": float((contactes_total / transmis) if transmis else 0.0),
        "taux_closing_sur_affectes": float((closing_total / transmis) if transmis else 0.0),
        "taux_closing_sur_traitements_total": float((closing_total / traitements_total) if traitements_total else 0.0),
    }


def compute_table_by_channel(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "Canal",
        "Traitements",
        "Closing",
        "Taux_closing_sur_traitements",
        "Clients_contactes",
        "Taux_contact_sur_transmis",
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)

    transmis = int(len(df))
    rows: List[Dict[str, Any]] = []

    for canal, col in CHANNEL_COLS:
        traitements = int(df[col].sum())
        closing = int((df["_is_closed"] & df["Canal"].eq(canal)).sum())
        clients_contactes = int((df[col] > 0).sum())  # nb clients touchés au moins 1 fois sur ce canal

        rows.append(
            {
                "Canal": canal,
                "Traitements": traitements,
                "Closing": closing,
                "Taux_closing_sur_traitements": float((closing / traitements) if traitements else 0.0),
                "Clients_contactes": clients_contactes,
                "Taux_contact_sur_transmis": float((clients_contactes / transmis) if transmis else 0.0),
            }
        )

    traitements_total = int(sum(r["Traitements"] for r in rows))
    closing_total = int(sum(r["Closing"] for r in rows))
    clients_contactes_any = int(df["_is_treated"].sum())

    rows.append(
        {
            "Canal": "Total",
            "Traitements": traitements_total,
            "Closing": closing_total,
            "Taux_closing_sur_traitements": float((closing_total / traitements_total) if traitements_total else 0.0),
            "Clients_contactes": clients_contactes_any,
            "Taux_contact_sur_transmis": float((clients_contactes_any / transmis) if transmis else 0.0),
        }
    )

    return pd.DataFrame(rows)[cols]


def compute_region_transmit_closed(df: pd.DataFrame) -> pd.DataFrame:
    """
    Retourne: Region | Transmis | Closed
    - Transmis = count lignes (affectées) par région
    - Closed = count lignes Action=Closed par région
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["Region", "Transmis", "Closed"])

    dim = load_clients_dim_regions()

    if dim.empty:
        tmp = df.copy()
        tmp["Region"] = "Inconnue"
    else:
        tmp = df.copy()
        tmp["Radical_compte"] = tmp["Radical_compte"].astype(str).str.strip()
        dim["radical_compte"] = dim["radical_compte"].astype(str).str.strip()
        tmp = tmp.merge(dim, left_on="Radical_compte", right_on="radical_compte", how="left")
        tmp["Region"] = tmp["Region"].replace({"": "Inconnue"}).fillna("Inconnue")

    g_transmis = tmp.groupby("Region", as_index=False).size().rename(columns={"size": "Transmis"})
    g_closed = tmp[tmp["_is_closed"]].groupby("Region", as_index=False).size().rename(columns={"size": "Closed"})

    out = g_transmis.merge(g_closed, on="Region", how="left").fillna(0)
    out["Closed"] = out["Closed"].astype(int)
    out["Transmis"] = out["Transmis"].astype(int)
    return out.sort_values("Transmis", ascending=False)


def compute_funnel_by_id_action(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["ID_Action", "Clients"])

    g = df.groupby("ID_Action", as_index=False).size().rename(columns={"size": "Clients"})

    def _sort_key(v: str) -> int:
        try:
            return int(str(v))
        except Exception:
            return 10**9

    return g.sort_values("ID_Action", key=lambda s: s.map(_sort_key))


def compute_daily_treatments_and_closed(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Date", "Traitements", "Closed"])

    tmp = df[df["_date_last_action"].notna()].copy()
    if tmp.empty:
        return pd.DataFrame(columns=["Date", "Traitements", "Closed"])

    tr = tmp[tmp["_is_treated"]].groupby("_date_last_action", as_index=False).size()
    tr = tr.rename(columns={"_date_last_action": "Date", "size": "Traitements"})

    cl = tmp[tmp["_is_closed"]].groupby("_date_last_action", as_index=False).size()
    cl = cl.rename(columns={"_date_last_action": "Date", "size": "Closed"})

    out = tr.merge(cl, on="Date", how="outer").fillna(0)
    out["Traitements"] = out["Traitements"].astype(int)
    out["Closed"] = out["Closed"].astype(int)
    return out.sort_values("Date")


# =========================================================
# Single-campaign graph payload (enrich node canal from modele)
# =========================================================
def _load_modele_for_campagne(campagne_id: str) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        camp = pd.read_sql_query(
            f"SELECT id_modele FROM {CAMPAGNES_TABLE} WHERE id_campagne = ?",
            conn,
            params=[str(campagne_id).strip()],
        )
        if camp.empty:
            return None

        id_modele = _norm_str(camp.iloc[0]["id_modele"])
        if not id_modele:
            return None

        mod = pd.read_sql_query(
            f"SELECT id_modele, nom_modele, liste_action, graphe_json FROM {MODELES_TABLE} WHERE id_modele = ?",
            conn,
            params=[id_modele],
        )
        if mod.empty:
            return None

        return mod.iloc[0].to_dict()
    finally:
        conn.close()


def build_graph_payload_for_single_campaign(df: pd.DataFrame, campagne_id: str) -> Dict[str, Any]:
    """
    Sortie:
    {
      "campaign_id": "...",
      "modele_id": "...",
      "modele_nom": "...",
      "nodes":[{"id":"5","label":"5 | Appel | Appeler (500)","count":500,"canal":"Appel","action":"Appeler"}],
      "edges":[{"from":"1","to":"2"}, ...]
    }
    """
    modele = _load_modele_for_campagne(campagne_id)
    if not modele:
        return {"campaign_id": campagne_id, "modele_id": "", "modele_nom": "", "nodes": [], "edges": []}

    # counts by ID_Action for THIS campaign (within already-filtered df)
    counts: Dict[str, int] = {}
    if df is not None and not df.empty:
        sub = df[df["ID_CAMPAGNE"].astype(str).str.strip().eq(str(campagne_id).strip())].copy()
        if not sub.empty:
            counts = sub.groupby("ID_Action").size().to_dict()

    graphe = _safe_json_loads(modele.get("graphe_json"), {"nodes": [], "edges": []})
    liste_action = _safe_json_loads(modele.get("liste_action"), [])

    # map id_action -> (canal, action) depuis liste_action
    id_to_meta: Dict[str, Dict[str, str]] = {}
    if isinstance(liste_action, list):
        for a in liste_action:
            nid = _norm_str(a.get("ID") or a.get("id"))
            if not nid:
                continue
            id_to_meta[nid] = {
                "canal": _norm_str(a.get("Canal")),
                "action": _norm_str(a.get("Action")),
            }

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, str]] = []

    # Prefer graphe_json if non-empty; else build from liste_action via Bloc_mère
    if isinstance(graphe, dict) and isinstance(graphe.get("nodes"), list) and graphe.get("nodes"):
        for n in graphe.get("nodes", []):
            nid = _norm_str(n.get("id") or n.get("ID") or n.get("node_id"))
            meta = id_to_meta.get(nid, {})
            canal = _norm_str(n.get("canal") or n.get("Canal")) or _norm_str(meta.get("canal"))
            action = _norm_str(n.get("action") or n.get("Action")) or _norm_str(meta.get("action"))

            cnt = int(counts.get(nid, 0))

            base_label = _norm_str(n.get("label"))
            if not base_label:
                base_label = f"{nid} | {canal} | {action}".strip(" |")
            else:
                if canal and canal not in base_label:
                    base_label = f"{base_label} | {canal}"
                if action and action not in base_label:
                    base_label = f"{base_label} | {action}"

            label = f"{base_label} ({cnt})"

            nodes.append({"id": nid, "label": label, "count": cnt, "canal": canal, "action": action})

        for e in graphe.get("edges", []):
            fr = _norm_str(e.get("from") or e.get("source") or e.get("src"))
            to = _norm_str(e.get("to") or e.get("target") or e.get("dst"))
            if fr and to:
                edges.append({"from": fr, "to": to})
    else:
        if isinstance(liste_action, list):
            for a in liste_action:
                nid = _norm_str(a.get("ID") or a.get("id"))
                canal = _norm_str(a.get("Canal"))
                action = _norm_str(a.get("Action"))
                parent = _norm_str(a.get("Bloc_mère") or a.get("bloc_mere") or a.get("parent"))
                cnt = int(counts.get(nid, 0))
                label = f"{nid} | {canal} | {action} ({cnt})"
                nodes.append({"id": nid, "label": label, "count": cnt, "canal": canal, "action": action})
                if parent:
                    edges.append({"from": parent, "to": nid})

    return {
        "campaign_id": str(campagne_id).strip(),
        "modele_id": _norm_str(modele.get("id_modele")),
        "modele_nom": _norm_str(modele.get("nom_modele")),
        "nodes": nodes,
        "edges": edges,
    }


# =========================================================
# Orchestrator (Streamlit + API)
# =========================================================
def compute_dashboard_payload(filters: DashboardFilters) -> Dict[str, Any]:
    df = load_clients_campagnes_df(filters)

    kpis = compute_kpis_compact(df)
    table_canal = compute_table_by_channel(df)
    region_mix = compute_region_transmit_closed(df)
    funnel = compute_funnel_by_id_action(df)
    daily = compute_daily_treatments_and_closed(df)

    payload: Dict[str, Any] = {
        "filters_applied": {
            "campagne_ids": filters.campagne_ids or [],
            "etats_campagne": filters.etats_campagne or [],
            "date_min": filters.date_min.isoformat() if filters.date_min else None,
            "date_max": filters.date_max.isoformat() if filters.date_max else None,
        },
        "kpis": kpis,
        "tables": {
            "by_channel": table_canal.to_dict(orient="records"),
        },
        "series": {
            "region_transmit_closed": region_mix.to_dict(orient="records"),
            "funnel_by_id_action": funnel.to_dict(orient="records"),
            "daily_treatments_closed": daily.to_dict(orient="records"),
        },
    }

    if filters.campagne_ids and len(filters.campagne_ids) == 1:
        payload["graph"] = build_graph_payload_for_single_campaign(df, filters.campagne_ids[0])

    return payload
