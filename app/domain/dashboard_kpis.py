from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

import pandas as pd

from app.storage.db import DB_PATH


# =========================
# Helpers
# =========================
def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _normalize_action(x: object) -> str:
    if x is None:
        return ""
    return str(x).strip().lower()


def _to_date_series(s: pd.Series) -> pd.Series:
    """Parse Date_last_action (TEXT) to a date series.

    Accepts either 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS' (or similar).
    """
    dt = pd.to_datetime(s, errors="coerce")
    return dt.dt.date


# =========================
# Data access
# =========================
CLIENTS_TABLE = "clients_campagnes"


@dataclass
class DashboardFilters:
    campagne_ids: Optional[List[str]] = None
    date_min: Optional[date] = None
    date_max: Optional[date] = None


def load_clients_campagnes_df(filters: DashboardFilters) -> pd.DataFrame:
    """Load client_campagne table as a DataFrame.

    Rules:
    - Excludes cancelled campaigns (Etat_campagne == 'Annulée') by default.
    - If campagne_ids provided, filters on those campaigns.
    - If date_min/max provided, filters on Date_last_action (parsed) within range.
    """
    where = ["COALESCE(Etat_campagne, '') <> 'Annulée'"]
    params: List[object] = []

    if filters.campagne_ids:
        placeholders = ",".join(["?"] * len(filters.campagne_ids))
        where.append(f"ID_CAMPAGNE IN ({placeholders})")
        params.extend(filters.campagne_ids)

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

    df["_action_norm"] = df.get("Action", "").apply(_normalize_action)
    df["_is_closed"] = df["_action_norm"].eq("closed")

    df["_has_last_action"] = df.get("Date_last_action", "").astype(str).str.strip().ne("")
    df["_date_last_action"] = _to_date_series(df.get("Date_last_action", pd.Series([None] * len(df))))

    if filters.date_min is not None:
        df = df[df["_date_last_action"].notna() & (df["_date_last_action"] >= filters.date_min)]
    if filters.date_max is not None:
        df = df[df["_date_last_action"].notna() & (df["_date_last_action"] <= filters.date_max)]

    for c in ["NB_appel", "NB_mail", "NB_sms", "NB_message"]:
        if c not in df.columns:
            df[c] = 0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    return df


# =========================
# KPI computation
# =========================
def compute_overview_kpis(df: pd.DataFrame) -> Dict[str, object]:
    """Compute main KPI cards for the dashboard."""
    if df is None or df.empty:
        return {
            "clients_transmis": 0,
            "clients_contactes": 0,
            "objectifs_atteints": 0,
            "clients_en_attente": 0,
            "clients_en_attente_en_traitement": 0,
            "nb_appel": 0,
            "nb_mail": 0,
            "nb_sms": 0,
            "nb_message": 0,
            "taux_reussite": 0.0,
            "taux_contact": 0.0,
        }

    clients_transmis = int(len(df))
    clients_contactes = int(df["_has_last_action"].sum())
    objectifs_atteints = int(df["_is_closed"].sum())

    en_attente_mask = df["_action_norm"].eq("en attente")
    clients_en_attente = int(en_attente_mask.sum())

    clients_en_attente_en_traitement = int(
        (en_attente_mask & df.get("Etat_campagne", "").astype(str).str.strip().eq("En cours")).sum()
    )

    nb_appel = int(df["NB_appel"].sum())
    nb_mail = int(df["NB_mail"].sum())
    nb_sms = int(df["NB_sms"].sum())
    nb_message = int(df["NB_message"].sum())

    taux_reussite = (objectifs_atteints / clients_transmis) if clients_transmis else 0.0
    taux_contact = (clients_contactes / clients_transmis) if clients_transmis else 0.0

    return {
        "clients_transmis": clients_transmis,
        "clients_contactes": clients_contactes,
        "objectifs_atteints": objectifs_atteints,
        "clients_en_attente": clients_en_attente,
        "clients_en_attente_en_traitement": clients_en_attente_en_traitement,
        "nb_appel": nb_appel,
        "nb_mail": nb_mail,
        "nb_sms": nb_sms,
        "nb_message": nb_message,
        "taux_reussite": float(taux_reussite),
        "taux_contact": float(taux_contact),
    }


def compute_success_by_channel(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Canal", "Clients", "Closed", "Taux_reussite"])

    rows = []
    mapping = {"Appel": "NB_appel", "Mail": "NB_mail", "SMS": "NB_sms", "Message": "NB_message"}
    for canal, col in mapping.items():
        pop = df[df[col] > 0]
        n_clients = int(len(pop))
        n_closed = int(pop["_is_closed"].sum()) if n_clients else 0
        taux = (n_closed / n_clients) if n_clients else 0.0
        rows.append({"Canal": canal, "Clients": n_clients, "Closed": n_closed, "Taux_reussite": float(taux)})

    return pd.DataFrame(rows)


def compute_daily_actions(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Date", "Actions"])

    tmp = df[df["_date_last_action"].notna()].copy()
    if tmp.empty:
        return pd.DataFrame(columns=["Date", "Actions"])

    g = tmp.groupby("_date_last_action", as_index=False).size()
    g = g.rename(columns={"_date_last_action": "Date", "size": "Actions"})
    g = g.sort_values("Date")
    return g


def compute_backlog_over_time(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Date", "Backlog_non_traite"])

    not_closed = df[~df["_is_closed"]].copy()
    if not_closed.empty:
        return pd.DataFrame(columns=["Date", "Backlog_non_traite"])

    dates = pd.date_range(date.today(), date.today(), freq="D")
    return pd.DataFrame({"Date": [d.date() for d in dates], "Backlog_non_traite": [int(len(not_closed)) for _ in dates]})


def compute_calls_before_success(df: pd.DataFrame) -> Dict[str, object]:
    if df is None or df.empty:
        return {"n_closed": 0, "moy_appels_closed": 0.0}

    closed = df[df["_is_closed"]].copy()
    n_closed = int(len(closed))
    if n_closed == 0:
        return {"n_closed": 0, "moy_appels_closed": 0.0}

    moy = float(closed["NB_appel"].mean()) if "NB_appel" in closed.columns else 0.0
    return {"n_closed": n_closed, "moy_appels_closed": moy}
