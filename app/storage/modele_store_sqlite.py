from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import pandas as pd
from psycopg import sql

from app.domain.modele import Modele
from app.storage.postgres_db import connection, ensure_table_columns

TABLE_NAME = "modeles"
EXPECTED_COLUMNS = {
    "id_modele",
    "nom_modele",
    "variable_cible",
    "objectif",
    "date_creation",
    "liste_action",
    "graphe_json",
    "ui_positions",
}


def ensure_modeles_table() -> None:
    ensure_table_columns(TABLE_NAME, EXPECTED_COLUMNS)


def _next_modele_id(cur) -> str:
    cur.execute(
        """
        SELECT id_modele
        FROM modeles
        WHERE id_modele ~ '^M[0-9]+$'
        ORDER BY CAST(SUBSTRING(id_modele FROM 2) AS BIGINT) DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return "M000001"
    match = re.search(r"(\d+)$", str(row[0]))
    number = int(match.group(1)) if match else 0
    return f"M{number + 1:06d}"


def list_modeles() -> List[Dict[str, Any]]:
    ensure_modeles_table()
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id_modele, nom_modele, date_creation, liste_action, graphe_json, ui_positions
                FROM modeles
                ORDER BY date_creation DESC
                """
            )
            return [dict(row) for row in cur.fetchall()]


def load_db() -> pd.DataFrame:
    rows = list_modeles()
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def get_modele_dict(id_modele: str) -> Optional[Dict[str, Any]]:
    ensure_modeles_table()
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id_modele, nom_modele, date_creation, liste_action, graphe_json, ui_positions
                FROM modeles
                WHERE id_modele = %s
                """,
                (id_modele,),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def insert_modele(modele: Modele) -> str:
    ensure_modeles_table()

    try:
        ui_positions_json = modele.ui_positions_str()
    except Exception:
        ui_positions_json = json.dumps(getattr(modele, "ui_positions", {}) or {}, ensure_ascii=False)
    try:
        liste_action_json = modele.liste_action_json()
    except Exception:
        liste_action_json = json.dumps(modele.liste_action or [], ensure_ascii=False)
    try:
        graphe_json = modele.graphe_json_str()
    except Exception:
        graphe_json = json.dumps(modele.graphe_json or {}, ensure_ascii=False)

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (620020,))
            if not modele.id_modele or not str(modele.id_modele).strip():
                modele.id_modele = _next_modele_id(cur)
            cur.execute(
                """
                INSERT INTO modeles (
                    id_modele, nom_modele, date_creation, liste_action, graphe_json, ui_positions
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    modele.id_modele,
                    modele.nom_modele,
                    modele.date_creation,
                    liste_action_json,
                    graphe_json,
                    ui_positions_json,
                ),
            )
    return str(modele.id_modele)


def delete_modele(id_modele: str) -> None:
    ensure_modeles_table()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM modeles WHERE id_modele = %s", (id_modele,))


def update_modele_field(id_modele: str, field: str, value: Any) -> None:
    ensure_modeles_table()
    allowed = {
        "nom_modele",
        "date_creation",
        "liste_action",
        "graphe_json",
        "ui_positions",
    }
    if field not in allowed:
        raise ValueError(f"Champ non supporté: {field}")
    query = sql.SQL("UPDATE modeles SET {} = %s WHERE id_modele = %s").format(sql.Identifier(field))
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (value, id_modele))


def dict_to_modele(d: Dict[str, Any]) -> Modele:
    try:
        liste_action = json.loads(d.get("liste_action") or "[]")
    except Exception:
        liste_action = []
    try:
        graphe = json.loads(d.get("graphe_json") or "{}")
    except Exception:
        graphe = {}
    try:
        ui_positions = json.loads(d.get("ui_positions") or "{}")
    except Exception:
        ui_positions = {}

    return Modele(
        id_modele=str(d.get("id_modele") or ""),
        nom_modele=str(d.get("nom_modele") or ""),
        date_creation=str(d.get("date_creation") or ""),
        liste_action=liste_action,
        graphe_json=graphe,
        ui_positions=ui_positions,
    )
