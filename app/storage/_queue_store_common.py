from __future__ import annotations

from typing import Sequence

from psycopg import sql

from app.storage.postgres_db import connection, ensure_table_columns

QUEUE_COLUMNS = [
    "ID_CAMPAGNE",
    "Radical_compte",
    "Numero_Tel",
    "Mail",
    "date_creation_campagne",
    "date_last_action",
    "ID_Action",
    "Canal",
    "Action",
    "Etat_campagne",
    "statut_avant_campagne",
    "statut_actuel",
]


def ensure_queue_table(table: str) -> None:
    ensure_table_columns(table, QUEUE_COLUMNS)


def clear_queue(table: str) -> None:
    ensure_queue_table(table)
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(table)))


def fill_queue_from_clients_campagnes(table: str, id_campagne: str, action: str) -> int:
    ensure_queue_table(table)

    update_columns = [column for column in QUEUE_COLUMNS if column not in {"ID_CAMPAGNE", "Radical_compte"}]
    update_set = sql.SQL(", ").join(
        sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(column), sql.Identifier(column))
        for column in update_columns
    )

    query = sql.SQL(
        """
        INSERT INTO {table} (
            "ID_CAMPAGNE", "Radical_compte", "Numero_Tel", "Mail",
            date_creation_campagne, date_last_action,
            "ID_Action", "Canal", "Action", "Etat_campagne",
            statut_avant_campagne, statut_actuel
        )
        SELECT
            cc."ID_CAMPAGNE",
            cc."Radical_compte",
            cl."Numero_Tel",
            cl."Mail",
            COALESCE(c.date_debut, '') AS date_creation_campagne,
            CASE
                WHEN COALESCE(cc.arriv_eche, '') = 'Oui'
                    THEN '0000-01-01 00:00:00'
                ELSE COALESCE(cc."Date_last_action", '')
            END AS date_last_action,
            COALESCE(cc."ID_Action", '') AS "ID_Action",
            COALESCE(cc."Canal", '') AS "Canal",
            COALESCE(cc."Action", '') AS "Action",
            COALESCE(cc."Etat_campagne", '') AS "Etat_campagne",
            '' AS statut_avant_campagne,
            '' AS statut_actuel
        FROM clients_campagnes AS cc
        LEFT JOIN clients AS cl
            ON cl.radical_compte = cc."Radical_compte"
        LEFT JOIN campagnes AS c
            ON c.id_campagne = cc."ID_CAMPAGNE"
        WHERE cc."ID_CAMPAGNE" = %s
          AND COALESCE(cc."Etat_campagne", '') = 'En cours'
          AND COALESCE(cc."Action", '') = %s
        ON CONFLICT ("ID_CAMPAGNE", "Radical_compte")
        DO UPDATE SET {update_set}
        """
    ).format(table=sql.Identifier(table), update_set=update_set)

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (id_campagne, action))
            count = cur.rowcount
    return int(count if count is not None and count >= 0 else 0)
