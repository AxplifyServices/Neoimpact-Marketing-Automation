from __future__ import annotations

from datetime import datetime
from typing import Iterable

from psycopg import sql

from app.storage.postgres_db import (
    connection,
    get_column_names,
    table_exists,
)


TABLE = "clients_cibles"
CIBLES_TABLE = "cibles"


# ============================================================
# SCHEMA VALIDATION
# ============================================================

def ensure_table() -> None:
    """
    Vérifie que la table clients_cibles possède bien
    le schéma attendu.

    Contrairement à l'ancienne version SQLite, le code
    applicatif ne crée plus ou ne modifie plus le schéma.

    Les modifications de structure passent exclusivement
    par les migrations SQL.
    """

    if not table_exists(TABLE):
        raise RuntimeError(
            f"La table PostgreSQL '{TABLE}' est absente."
        )

    columns = set(
        get_column_names(TABLE)
    )

    expected = {
        "ID_CIBLE",
        "Radical_compte",
        "created_at",
    }

    missing = (
        expected - columns
    )

    if missing:
        missing_list = ", ".join(
            sorted(missing)
        )

        raise RuntimeError(
            f"Schéma PostgreSQL invalide pour '{TABLE}'. "
            f"Colonnes absentes : {missing_list}"
        )


# ============================================================
# INSERT-ONLY MEMBERSHIP
# ============================================================

def insert_only_members(
    id_cible: str,
    radicals: Iterable[str],
) -> int:
    """
    Ajoute uniquement les nouveaux couples :

        (ID_CIBLE, Radical_compte)

    Aucun membre existant n'est supprimé.

    Les doublons sont ignorés grâce à la contrainte UNIQUE
    PostgreSQL existante.
    """

    ensure_table()

    id_cible = str(
        id_cible or ""
    ).strip()

    if not id_cible:
        return 0

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Normalisation + déduplication du batch fourni.
    unique_radicals = list(
        dict.fromkeys(
            str(rc).strip()
            for rc in radicals
            if str(rc).strip()
        )
    )

    if not unique_radicals:
        return 0

    data = [
        (
            id_cible,
            radical,
            now,
        )
        for radical in unique_radicals
    ]

    query = """
        INSERT INTO clients_cibles (
            "ID_CIBLE",
            "Radical_compte",
            created_at
        )
        VALUES (%s, %s, %s)
        ON CONFLICT (
            "ID_CIBLE",
            "Radical_compte"
        )
        DO NOTHING
    """

    with connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                query,
                data,
            )

            inserted = int(
                cur.rowcount or 0
            )

    return inserted


# ============================================================
# VOLUME
# ============================================================

def get_volume(
    id_cible: str,
) -> int:
    """
    Retourne le nombre de clients actuellement associés
    à une cible.
    """

    ensure_table()

    query = """
        SELECT COUNT(*)
        FROM clients_cibles
        WHERE "ID_CIBLE" = %s
    """

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (id_cible,),
            )

            row = cur.fetchone()

    if not row:
        return 0

    return int(
        row[0] or 0
    )


# ============================================================
# OPTIONAL CIBLE VOLUME
# ============================================================

def update_cible_volume_if_column_exists(
    id_cible: str,
) -> None:
    """
    Met à jour cibles.volume ou cibles.Volume uniquement
    si cette colonne existe.

    Dans le schéma PostgreSQL actuel, aucune de ces colonnes
    n'existe : la fonction fait donc volontairement un no-op.

    Ce comportement conserve la compatibilité avec l'ancien
    code sans inventer une colonne supplémentaire.
    """

    if not table_exists(CIBLES_TABLE):
        raise RuntimeError(
            f"La table PostgreSQL '{CIBLES_TABLE}' est absente."
        )

    columns = set(
        get_column_names(CIBLES_TABLE)
    )

    if "volume" in columns:
        volume_column = "volume"
    elif "Volume" in columns:
        volume_column = "Volume"
    else:
        return

    if "id_cible" in columns:
        id_column = "id_cible"
    elif "ID_CIBLE" in columns:
        id_column = "ID_CIBLE"
    else:
        raise RuntimeError(
            "La table 'cibles' ne possède ni "
            "'id_cible' ni 'ID_CIBLE'."
        )

    volume = get_volume(
        id_cible
    )

    query = sql.SQL(
        """
        UPDATE {table}
        SET {volume_column} = %s
        WHERE {id_column} = %s
        """
    ).format(
        table=sql.Identifier(
            CIBLES_TABLE
        ),
        volume_column=sql.Identifier(
            volume_column
        ),
        id_column=sql.Identifier(
            id_column
        ),
    )

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    volume,
                    id_cible,
                ),
            )