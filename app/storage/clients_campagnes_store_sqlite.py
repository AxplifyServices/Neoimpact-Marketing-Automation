from __future__ import annotations

from itertools import chain
from typing import Any, Dict, Iterable, List

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
    "Creneau",
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
    ensure_table_columns(TABLE_NAME, ["id", *COLUMNS, "row_status"])


def bulk_insert_clients(rows: Iterable[Dict[str, Any]]) -> int:
    """Insère un flux de lignes sans construire une seconde matrice en mémoire."""
    iterator = iter(rows)
    try:
        first = next(iterator)
    except StopIteration:
        return 0

    ensure_table()

    def _iter_values():
        for source in chain((first,), iterator):
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
            row.setdefault("Creneau", "Indifferent")
            yield tuple(row.get(column) for column in COLUMNS)

    query = sql.SQL("INSERT INTO {table} ({columns}) VALUES ({placeholders})").format(
        table=sql.Identifier(TABLE_NAME),
        columns=sql.SQL(", " ).join(sql.Identifier(c) for c in COLUMNS),
        placeholders=sql.SQL(", " ).join(sql.Placeholder() for _ in COLUMNS),
    )

    with connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(query, _iter_values())
            count = cur.rowcount
    return int(count if count is not None and count >= 0 else 0)



def bulk_insert_clients_from_radical_select(
    radical_select,
    select_params: List[Any],
    row_template: Dict[str, Any],
    *,
    only_new: bool = False,
) -> int:
    """INSERT ... SELECT PostgreSQL natif depuis une colonne Radical_compte."""
    ensure_table()
    template = dict(row_template or {})
    template.setdefault("arriv_eche", "Non")
    template.setdefault("date_debut_campagne", None)
    template.setdefault("nb_jour_debut_campagne", 0)
    template.setdefault("conversion", 0)
    template.setdefault("conversion_date", None)
    template.setdefault("conversion_id_action", None)
    template.setdefault("conversion_canal", None)
    template.setdefault("objective_source_id_action", None)
    template.setdefault("objective_source_canal", None)
    template.setdefault("Creneau", "Indifferent")

    select_exprs = []
    constant_params: List[Any] = []
    for column in COLUMNS:
        if column == "Radical_compte":
            select_exprs.append(sql.SQL('src."Radical_compte"'))
        else:
            select_exprs.append(sql.Placeholder())
            constant_params.append(template.get(column))

    where_parts = [sql.SQL("TRIM(COALESCE(src.\"Radical_compte\"::text, '')) <> ''")]
    trailing_params: List[Any] = []
    if only_new:
        where_parts.append(sql.SQL("""
            NOT EXISTS (
                SELECT 1 FROM clients_campagnes existing
                WHERE existing."ID_CAMPAGNE" = %s
                  AND existing."Radical_compte" = src."Radical_compte"
            )
        """))
        trailing_params.append(template.get("ID_CAMPAGNE"))

    query = sql.SQL("""
        INSERT INTO {table} ({columns})
        SELECT {select_exprs}
        FROM ({radical_select}) AS src
        WHERE {where_clause}
    """).format(
        table=sql.Identifier(TABLE_NAME),
        columns=sql.SQL(", " ).join(sql.Identifier(c) for c in COLUMNS),
        select_exprs=sql.SQL(", " ).join(select_exprs),
        radical_select=radical_select,
        where_clause=sql.SQL(" AND " ).join(where_parts),
    )
    params = [*constant_params, *(select_params or []), *trailing_params]
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            count = cur.rowcount
    return int(count if count is not None and count >= 0 else 0)

def set_clients_etat_for_campagne(id_campagne: str, etat: str) -> int:
    """Compatibilité historique, sans UPDATE massif.

    Depuis la migration 013, l'état global courant vit exclusivement dans
    ``campagnes.etat_campagne``. Mettre en pause/activer/terminer une campagne
    ne doit plus réécrire N millions de lignes dans ``clients_campagnes``.

    ``clients_campagnes.Etat_campagne`` reste un snapshot legacy et
    ``row_status`` porte uniquement la neutralisation individuelle d'un client.
    """
    ensure_table()
    return 0
