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


def _clean_campagne_id(x: object) -> str:
    """
    Normalise un id campagne venant potentiellement de l'UI/API.
    Exemple: 'CP000029|' -> 'CP000029'
    """
    s = _norm_str(x)
    s = s.replace("\u200b", "")  # zero-width space si jamais
    s = s.strip().rstrip("|").strip()
    return s


def _to_int_series_safe(s: pd.Series, default: int = 0) -> pd.Series:
    """Coerce une série en int (NaN -> default)."""
    try:
        out = pd.to_numeric(s, errors="coerce").fillna(default).astype(int)
        return out
    except Exception:
        return pd.Series([default] * len(s), index=s.index)


def _compute_is_converted(df: pd.DataFrame) -> pd.Series:
    """
    Source de vérité conversion:
      - colonne 'conversion' (int) : conversion == 1
    Si colonne absente => tout à 0 (pas de conversion).
    """
    if df is None or df.empty:
        return pd.Series([], dtype=bool)

    if "conversion" not in df.columns:
        return pd.Series([False] * len(df), index=df.index)

    conv = _to_int_series_safe(df["conversion"], default=0)
    return conv.eq(1)


# =========================================================
# Filters model
# =========================================================
@dataclass
class DashboardFilters:
    campagne_ids: Optional[List[str]] = None
    etats_campagne: Optional[List[str]] = None  # "Terminée", "En cours", "En pause"
    date_min: Optional[date] = None
    date_max: Optional[date] = None
    gestionnaires: Optional[List[str]] = None  # ✅ NEW


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
    where = ["COALESCE(Etat_campagne,'') <> 'Annulée'"]
    params: List[object] = []

    where.append("COALESCE(Etat_campagne,'') IN ('Terminée','En cours','En pause')")

    if filters.campagne_ids:
        placeholders = ",".join(["?"] * len(filters.campagne_ids))
        where.append(f"ID_CAMPAGNE IN ({placeholders})")
        params.extend([_clean_campagne_id(x) for x in filters.campagne_ids])

    if filters.etats_campagne:
        placeholders = ",".join(["?"] * len(filters.etats_campagne))
        where.append(f"Etat_campagne IN ({placeholders})")
        params.extend([str(x).strip() for x in filters.etats_campagne])

    if filters.gestionnaires:
        placeholders = ",".join(["?"] * len(filters.gestionnaires))
        where.append(f"COALESCE(cl.Gestionnaire,'') IN ({placeholders})")
        params.extend([str(x).strip() for x in filters.gestionnaires])

    # ✅ SELECT explicite pour garantir la colonne Gestionnaire
    sql = f"""
    SELECT cc.*, cl.Gestionnaire AS Gestionnaire
    FROM {CLIENTS_TABLE} cc
    LEFT JOIN {CLIENTS_DIM_TABLE} cl ON cl.radical_compte = cc.Radical_compte
    """

    if where:
        sql += " WHERE " + " AND ".join(where)

    conn = _connect()
    try:
        df = pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()

    if df.empty:
        return df

    # ---------------------------------------------------------
    # Flags standardisés
    # ---------------------------------------------------------
    df["_action_norm"] = df.get("Action", "").apply(_normalize_action)

    # ✅ Nouveau: conversion = 1 est la vérité
    df["_is_converted"] = _compute_is_converted(df)

    df["ID_Action"] = df.get("ID_Action", "").astype(str).str.strip()
    df["Canal"] = df.get("Canal", "").astype(str).str.strip()
    df["ID_CAMPAGNE"] = df.get("ID_CAMPAGNE", "").astype(str).str.strip()

    df["_has_last_action"] = df.get("Date_last_action", "").astype(str).str.strip().ne("")
    df["_date_last_action"] = _to_date_series(df.get("Date_last_action", pd.Series([None] * len(df))))

    df["_is_treated"] = df["_has_last_action"] & df["ID_Action"].ne("1")

    if filters.date_min is not None:
        df = df[df["_date_last_action"].notna() & (df["_date_last_action"] >= filters.date_min)]
    if filters.date_max is not None:
        df = df[df["_date_last_action"].notna() & (df["_date_last_action"] <= filters.date_max)]

    for _, col in CHANNEL_COLS:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # s'assure que conversion existe (utile pour affichage / compat)
    if "conversion" not in df.columns:
        df["conversion"] = 0
    else:
        df["conversion"] = _to_int_series_safe(df["conversion"], default=0)

    return df


##################################################################################################
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
            "closing_total": 0,  # (compat) = conversions
            "traitements_total": 0,
            "taux_contact_total": 0.0,
            "taux_closing_sur_affectes": 0.0,  # (compat) = taux conversion / affectés
            "taux_closing_sur_traitements_total": 0.0,  # (compat)
            "arriv_eche": 0,
        }

    transmis = int(len(df))
    contactes_total = int(df["_is_treated"].sum())

    # ✅ conversion remplace "closed"
    closing_total = int(df["_is_converted"].sum())

    traitements_total = int(sum(df[col].sum() for _, col in CHANNEL_COLS))
    arriv_eche = compute_arriv_eche_oui(df)

    return {
        "transmis": transmis,
        "contactes_total": contactes_total,
        "closing_total": closing_total,
        "traitements_total": traitements_total,
        "arriv_eche": arriv_eche,
        "taux_contact_total": float((contactes_total / transmis) if transmis else 0.0),
        "taux_closing_sur_affectes": float((closing_total / transmis) if transmis else 0.0),
        "taux_closing_sur_traitements_total": float((closing_total / traitements_total) if traitements_total else 0.0),
    }


def compute_arriv_eche_oui(df: pd.DataFrame) -> int:
    """KPI: nombre de clients arrivant à échéance = nombre de 'Oui' dans la colonne arriv_eche."""
    if df is None or df.empty:
        return 0
    if "arriv_eche" not in df.columns:
        return 0
    s = df["arriv_eche"].astype(str).str.strip().str.lower()
    return int((s == "oui").sum())


def compute_table_by_channel(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "Canal",
        "Traitements",
        "Closing",  # (compat) = conversions
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

        # ✅ conversion remplace closed
        closing = int((df["_is_converted"] & df["Canal"].eq(canal)).sum())

        clients_contactes = int((df[col] > 0).sum())

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
    ⚠️ (compat) "Closed" = conversions (conversion==1)
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

    # ✅ conversions par région (colonne conservée "Closed" pour compat UI)
    g_closed = tmp[tmp["_is_converted"]].groupby("Region", as_index=False).size().rename(columns={"size": "Closed"})

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
    """
    Retourne: Date | Traitements | Closed
    ⚠️ (compat) "Closed" = conversions (conversion==1)
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["Date", "Traitements", "Closed"])

    tmp = df[df["_date_last_action"].notna()].copy()
    if tmp.empty:
        return pd.DataFrame(columns=["Date", "Traitements", "Closed"])

    tr = tmp[tmp["_is_treated"]].groupby("_date_last_action", as_index=False).size()
    tr = tr.rename(columns={"_date_last_action": "Date", "size": "Traitements"})

    # ✅ conversions/jour (colonne conservée "Closed" pour compat UI)
    cl = tmp[tmp["_is_converted"]].groupby("_date_last_action", as_index=False).size()
    cl = cl.rename(columns={"_date_last_action": "Date", "size": "Closed"})

    out = tr.merge(cl, on="Date", how="outer").fillna(0)
    out["Traitements"] = out["Traitements"].astype(int)
    out["Closed"] = out["Closed"].astype(int)
    return out.sort_values("Date")


# =========================================================
# Helpers: per-campaign isolation (for API)
# =========================================================
def _split_df_by_campaign(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    if df is None or df.empty or "ID_CAMPAGNE" not in df.columns:
        return {}
    out: Dict[str, pd.DataFrame] = {}
    for cid, sub in df.groupby("ID_CAMPAGNE"):
        out[str(cid).strip()] = sub.copy()
    return out


def _compute_payload_isolated_for_campaign(df_all: pd.DataFrame, cid: str) -> Dict[str, Any]:
    sub = df_all[df_all["ID_CAMPAGNE"].astype(str).str.strip().eq(str(cid).strip())].copy()

    kpis = compute_kpis_compact(sub)
    table_canal = compute_table_by_channel(sub)
    region_mix = compute_region_transmit_closed(sub)
    funnel = compute_funnel_by_id_action(sub)
    daily = compute_daily_treatments_and_closed(sub)

    out: Dict[str, Any] = {
        "campagne_id": str(cid).strip(),
        "kpis": kpis,
        "tables": {
            "by_channel": table_canal.to_dict(orient="records"),
        },
        "series": {
            "region_transmit_closed": region_mix.to_dict(orient="records"),
            "funnel_by_id_action": funnel.to_dict(orient="records"),
            "daily_treatments_closed": daily.to_dict(orient="records"),
        },
        "graph": build_graph_payload_for_single_campaign(df_all, str(cid).strip()),
    }
    return out


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
    campagne_id = _clean_campagne_id(campagne_id)
    """
    Sortie:
    {
      "campaign_id": "...",
      "modele_id": "...",
      "modele_nom": "...",
      "nodes":[
         {"id":"5","label":"5 | Appel | Appeler (500 | 12 conv)",
          "count":500,"converted_count":12,"canal":"Appel","action":"Appeler"}
      ],
      "edges":[{"from":"1","to":"2"}, ...]
    }
    """
    modele = _load_modele_for_campagne(campagne_id)
    if not modele:
        return {"campaign_id": campagne_id, "modele_id": "", "modele_nom": "", "nodes": [], "edges": []}

    counts: Dict[str, int] = {}
    conv_counts: Dict[str, int] = {}

    if df is not None and not df.empty:
        sub = df[df["ID_CAMPAGNE"].astype(str).str.strip().eq(str(campagne_id).strip())].copy()
        if not sub.empty:
            counts = sub.groupby("ID_Action").size().to_dict()

            # ✅ conversions par noeud (ID_Action)
            if "_is_converted" in sub.columns:
                conv_counts = sub[sub["_is_converted"]].groupby("ID_Action").size().to_dict()
            else:
                conv_counts = {}

    graphe = _safe_json_loads(modele.get("graphe_json"), {"nodes": [], "edges": []})
    liste_action = _safe_json_loads(modele.get("liste_action"), [])

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

    if isinstance(graphe, dict) and isinstance(graphe.get("nodes"), list) and graphe.get("nodes"):
        for n in graphe.get("nodes", []):
            nid = _norm_str(n.get("id") or n.get("ID") or n.get("node_id"))
            meta = id_to_meta.get(nid, {})
            canal = _norm_str(n.get("canal") or n.get("Canal")) or _norm_str(meta.get("canal"))
            action = _norm_str(n.get("action") or n.get("Action")) or _norm_str(meta.get("action"))

            cnt = int(counts.get(nid, 0))
            conv = int(conv_counts.get(nid, 0))

            base_label = _norm_str(n.get("label"))
            if not base_label:
                base_label = f"{nid} | {canal} | {action}".strip(" |")
            else:
                if canal and canal not in base_label:
                    base_label = f"{base_label} | {canal}"
                if action and action not in base_label:
                    base_label = f"{base_label} | {action}"

            label = f"{base_label} ({cnt} | {conv} conv)"

            nodes.append(
                {
                    "id": nid,
                    "label": label,
                    "count": cnt,
                    "converted_count": conv,
                    "canal": canal,
                    "action": action,
                }
            )

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
                conv = int(conv_counts.get(nid, 0))

                label = f"{nid} | {canal} | {action} ({cnt} | {conv} conv)"

                nodes.append(
                    {
                        "id": nid,
                        "label": label,
                        "count": cnt,
                        "converted_count": conv,
                        "canal": canal,
                        "action": action,
                    }
                )

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
        "tables": {"by_channel": table_canal.to_dict(orient="records")},
        "series": {
            "region_transmit_closed": region_mix.to_dict(orient="records"),
            "funnel_by_id_action": funnel.to_dict(orient="records"),
            "daily_treatments_closed": daily.to_dict(orient="records"),
        },
    }

    if filters.campagne_ids and len(filters.campagne_ids) == 1:
        payload["graph"] = build_graph_payload_for_single_campaign(df, _clean_campagne_id(filters.campagne_ids[0]))

    if filters.campagne_ids:
        by_campaign: Dict[str, Any] = {}
        for raw in (filters.campagne_ids or []):
            cid = _clean_campagne_id(raw)
            if not cid:
                continue
            by_campaign[cid] = _compute_payload_isolated_for_campaign(df, cid)
        payload["by_campaign"] = by_campaign

    return payload


# =========================================================
# Arrivant échéance (helpers existants inchangés)
# =========================================================
def _extract_deadline_days_from_node(node: dict) -> List[int]:
    out = []
    conditions = node.get("conditions") or []
    if not isinstance(conditions, list):
        return out

    for c in conditions:
        field = str(c.get("field", "")).lower()
        if field in (
            "nb_jour_last_action",
            "nb_jours_last_action",
            "days_since_last_action",
        ):
            try:
                out.append(int(c.get("value")))
            except Exception:
                pass

    return out


def compute_clients_arrivant_echeance(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0

    today = date.today()
    total_flagged = 0

    for campagne_id, sub_df in df.groupby("ID_CAMPAGNE"):
        modele = _load_modele_for_campagne(campagne_id)
        if not modele:
            continue

        graphe = _safe_json_loads(modele.get("graphe_json"), {})
        nodes = graphe.get("nodes", [])
        edges = graphe.get("edges", [])

        if not nodes or not edges:
            continue

        children_map: Dict[str, List[str]] = {}
        for e in edges:
            parent = str(e.get("from")).strip()
            child = str(e.get("to")).strip()
            children_map.setdefault(parent, []).append(child)

        node_by_id = {str(n.get("id")).strip(): n for n in nodes if n.get("id") is not None}

        for _, row in sub_df.iterrows():
            id_action = str(row.get("ID_Action", "")).strip()
            date_last = row.get("_date_last_action")

            if not id_action or not date_last:
                continue

            days_elapsed = (today - date_last).days
            children_ids = children_map.get(id_action, [])

            flagged = False
            for cid in children_ids:
                child_node = node_by_id.get(cid)
                if not child_node:
                    continue

                deadlines = _extract_deadline_days_from_node(child_node)
                for d in deadlines:
                    if days_elapsed == d - 1:
                        flagged = True
                        break
                if flagged:
                    break

            if flagged:
                total_flagged += 1

    return total_flagged
