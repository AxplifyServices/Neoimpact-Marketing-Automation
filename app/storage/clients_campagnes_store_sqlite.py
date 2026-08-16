from __future__ import annotations

from typing import Any, Dict, List

from psycopg import sql

from app.storage.postgres_db import connection, ensure_table_columns

TABLE_NAME = "clients_campagnes"

COLUMNS = [
    "Nom_campagne",
    "ID_CAMPAGNE",
    "Radical_compte",
    "Etat_campagne",
    "NB_jour_campagne",
    "ID_Action",
    "Canal",
    "Action",
    "Last_action",
    "Resultat_last_action",
    "Date_last_action",
    "NB_jour_last_action",
    "NB_appel",
    "NB_mail",
    "NB_sms",
    "NB_message",
    "NB_approche_commercial",
    "NB_da",
    "NB_cc",
    "NB_push",
    "arriv_eche",
    "date_debut_campagne",
    "nb_jour_debut_campagne",
    "conversion",
    "conversion_date",
    "conversion_id_action",
    "conversion_canal",
    "objective_source_id_action",
    "objective_source_canal",
]


def ensure_table() -> None:
    ensure_table_columns(TABLE_NAME, ["id", *COLUMNS])


def bulk_insert_clients(rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    ensure_table()

    values = []
    for source in rows:
        row = dict(source)
        row.setdefault("arriv_eche", "Non")
        if row.get("arriv_eche") is None:
            row["arriv_eche"] = "Non"
        row.setdefault("date_debut_campagne", None)
        if row.get("nb_jour_debut_campagne") is None:
            row["nb_jour_debut_campagne"] = 0
        if row.get("conversion") is None:
            row["conversion"] = 0
        row.setdefault("conversion_date", None)
        row.setdefault("conversion_id_action", None)
        row.setdefault("conversion_canal", None)
        row.setdefault("objective_source_id_action", None)
        row.setdefault("objective_source_canal", None)
        values.append([row.get(column) for column in COLUMNS])

    query = sql.SQL("INSERT INTO {table} ({columns}) VALUES ({placeholders})").format(
        table=sql.Identifier(TABLE_NAME),
        columns=sql.SQL(", ").join(sql.Identifier(c) for c in COLUMNS),
        placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in COLUMNS),
    )

    with connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(query, values)
            count = cur.rowcount
    return int(count if count is not None and count >= 0 else len(values))


def set_clients_etat_for_campagne(id_campagne: str, etat: str) -> int:
    ensure_table()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'UPDATE clients_campagnes SET "Etat_campagne" = %s WHERE "ID_CAMPAGNE" = %s',
                (etat, id_campagne),
            )
            count = cur.rowcount
    return int(count if count is not None and count >= 0 else 0)
