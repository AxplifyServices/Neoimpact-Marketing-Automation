from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple

import psycopg
from dotenv import load_dotenv
from psycopg import Connection, sql
from psycopg.rows import dict_row


# ============================================================
# ENV
# ============================================================

load_dotenv()


def _env(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)

    if value is None:
        raise RuntimeError(
            f"Variable d'environnement obligatoire absente : {name}"
        )

    return str(value).strip()


def get_database_url() -> str:
    """
    Retourne la DATABASE_URL PostgreSQL.

    Exemple local :
      postgresql://neoimpact_app:password@127.0.0.1:5433/neoimpact_marketing
    """
    value = os.getenv("DATABASE_URL")

    if value and value.strip():
        return value.strip()

    host = _env("POSTGRES_HOST", "127.0.0.1")
    port = _env("POSTGRES_PORT", "5433")
    database = _env("POSTGRES_DB", "neoimpact_marketing")
    user = _env("POSTGRES_USER", "neoimpact_app")
    password = _env("POSTGRES_PASSWORD")

    return (
        f"postgresql://{user}:{password}"
        f"@{host}:{port}/{database}"
    )


# ============================================================
# CONNECTIONS
# ============================================================

def get_connection(
    *,
    dict_rows: bool = False,
    autocommit: bool = False,
) -> Connection:
    """
    Ouvre une connexion PostgreSQL.

    dict_rows=False :
        fetchone() -> tuple

    dict_rows=True :
        fetchone() -> dict
    """

    kwargs: Dict[str, Any] = {
        "conninfo": get_database_url(),
        "autocommit": autocommit,
    }

    if dict_rows:
        kwargs["row_factory"] = dict_row

    return psycopg.connect(**kwargs)


@contextmanager
def connection(
    *,
    dict_rows: bool = False,
    autocommit: bool = False,
) -> Iterator[Connection]:
    """
    Context manager commun pour les accès PostgreSQL.
    """

    conn = get_connection(
        dict_rows=dict_rows,
        autocommit=autocommit,
    )

    try:
        yield conn

        if not autocommit:
            conn.commit()

    except Exception:
        if not autocommit:
            conn.rollback()

        raise

    finally:
        conn.close()


# ============================================================
# IDENTIFIANTS SQL
# ============================================================

def identifier(name: str) -> sql.Identifier:
    """
    Produit un identifiant PostgreSQL correctement quoté.

    Important pour les anciennes colonnes à casse mixte comme :
      ID_CAMPAGNE
      Radical_compte
      Nom
      Mail

    sql.Identifier("ID_CAMPAGNE")
    deviendra :
      "ID_CAMPAGNE"
    """

    if not isinstance(name, str):
        raise TypeError("Le nom SQL doit être une chaîne.")

    name = name.strip()

    if not name:
        raise ValueError("Le nom SQL ne peut pas être vide.")

    return sql.Identifier(name)


# ============================================================
# INTROSPECTION POSTGRESQL
# ============================================================

def list_tables() -> List[str]:
    """
    Liste uniquement les tables applicatives du schéma public.
    """

    query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

    return [str(row[0]) for row in rows]


def table_exists(table: str) -> bool:
    """
    Vérifie qu'une table existe dans public.
    """

    query = """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
              AND table_name = %s
        )
    """

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (table,))
            row = cur.fetchone()

    return bool(row and row[0])


def get_table_columns(table: str) -> List[Tuple[str, str]]:
    """
    Retourne :
        [(nom_colonne, type_postgresql), ...]

    dans l'ordre physique du schéma.
    """

    query = """
        SELECT
            column_name,
            CASE
                WHEN data_type = 'USER-DEFINED'
                    THEN udt_name
                ELSE data_type
            END AS column_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        ORDER BY ordinal_position
    """

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (table,))
            rows = cur.fetchall()

    return [
        (str(row[0]), str(row[1] or ""))
        for row in rows
    ]


def get_column_names(table: str) -> List[str]:
    return [
        name
        for name, _ in get_table_columns(table)
    ]


def column_exists(table: str, column: str) -> bool:
    query = """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
        )
    """

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (table, column))
            row = cur.fetchone()

    return bool(row and row[0])


# ============================================================
# VALUES
# ============================================================

def normalize_value(value: Any) -> Any:
    """
    Normalise une valeur avant insertion PostgreSQL.

    La gestion spécifique Pandas sera ajoutée plus tard,
    au moment de migrer les modules qui manipulent réellement
    des DataFrames.
    """

    if value is None:
        return None

    return value


# ============================================================
# READ HELPERS
# ============================================================

def fetch_all(
    query: Any,
    params: Optional[Tuple[Any, ...] | List[Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Exécute un SELECT et retourne une liste de dictionnaires.
    """

    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            rows = cur.fetchall()

    return [dict(row) for row in rows]


def fetch_one(
    query: Any,
    params: Optional[Tuple[Any, ...] | List[Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Exécute un SELECT et retourne une ligne dictionnaire.
    """

    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()

    if row is None:
        return None

    return dict(row)

    """
    Exécute une requête et produit directement un DataFrame.

    On ne dépend volontairement pas de pd.read_sql_query ici,
    afin de garder psycopg comme couche SQL explicite.
    """

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())

            if cur.description is None:
                return pd.DataFrame()

            columns = [
                desc.name
                for desc in cur.description
            ]

            rows = cur.fetchall()

    return pd.DataFrame(
        rows,
        columns=columns,
    )


# ============================================================
# HEALTHCHECK
# ============================================================

def healthcheck() -> Dict[str, Any]:
    """
    Vérifie la connexion et retourne quelques informations
    permettant de confirmer qu'on parle à la bonne base.
    """

    query = """
        SELECT
            current_database() AS database_name,
            current_user AS database_user,
            version() AS postgres_version
    """

    row = fetch_one(query)

    if row is None:
        raise RuntimeError(
            "PostgreSQL n'a retourné aucune information."
        )

    return {
        "ok": True,
        "database": row.get("database_name"),
        "user": row.get("database_user"),
        "version": row.get("postgres_version"),
        "tables": len(list_tables()),
    }