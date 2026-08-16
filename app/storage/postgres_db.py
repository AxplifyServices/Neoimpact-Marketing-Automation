from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

import psycopg
from dotenv import load_dotenv
from psycopg import Connection, sql
from psycopg.rows import dict_row

load_dotenv()


def _env(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Variable d'environnement obligatoire absente : {name}")
    return str(value).strip()


def get_database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if value and value.strip():
        return value.strip()

    host = _env("POSTGRES_HOST", "127.0.0.1")
    port = _env("POSTGRES_PORT", "5433")
    database = _env("POSTGRES_DB", "neoimpact_marketing")
    user = _env("POSTGRES_USER", "neoimpact_app")
    password = _env("POSTGRES_PASSWORD")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def get_connection(*, dict_rows: bool = False, autocommit: bool = False) -> Connection:
    kwargs: Dict[str, Any] = {
        "conninfo": get_database_url(),
        "autocommit": autocommit,
        "connect_timeout": 5,
    }
    if dict_rows:
        kwargs["row_factory"] = dict_row
    return psycopg.connect(**kwargs)


@contextmanager
def connection(*, dict_rows: bool = False, autocommit: bool = False) -> Iterator[Connection]:
    conn = get_connection(dict_rows=dict_rows, autocommit=autocommit)
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


def identifier(name: str) -> sql.Identifier:
    if not isinstance(name, str):
        raise TypeError("Le nom SQL doit être une chaîne.")
    value = name.strip()
    if not value:
        raise ValueError("Le nom SQL ne peut pas être vide.")
    return sql.Identifier(value)


def list_tables() -> List[str]:
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
            return [str(row[0]) for row in cur.fetchall()]


def table_exists(table: str) -> bool:
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
    query = """
        SELECT
            column_name,
            CASE WHEN data_type = 'USER-DEFINED' THEN udt_name ELSE data_type END AS column_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        ORDER BY ordinal_position
    """
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (table,))
            rows = cur.fetchall()
    return [(str(row[0]), str(row[1] or "")) for row in rows]


def get_column_names(table: str) -> List[str]:
    return [name for name, _ in get_table_columns(table)]


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


def ensure_table_columns(table: str, expected: Sequence[str]) -> None:
    if not table_exists(table):
        raise RuntimeError(f"La table PostgreSQL '{table}' est absente.")
    existing = set(get_column_names(table))
    missing = set(expected) - existing
    if missing:
        raise RuntimeError(
            f"Schéma PostgreSQL invalide pour '{table}'. Colonnes absentes : "
            + ", ".join(sorted(missing))
        )


def get_row_identity_columns(table: str) -> List[str]:
    """Retourne la PK, sinon la première contrainte/index UNIQUE exploitable."""
    query = """
        SELECT
            i.indisprimary,
            i.indisunique,
            array_agg(a.attname ORDER BY x.n) AS columns
        FROM pg_class t
        JOIN pg_namespace ns ON ns.oid = t.relnamespace
        JOIN pg_index i ON i.indrelid = t.oid
        JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS x(attnum, n) ON TRUE
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = x.attnum
        WHERE ns.nspname = 'public'
          AND t.relname = %s
          AND (i.indisprimary OR i.indisunique)
          AND i.indpred IS NULL
        GROUP BY i.indexrelid, i.indisprimary, i.indisunique
        ORDER BY i.indisprimary DESC, array_length(array_agg(a.attname), 1) ASC
        LIMIT 1
    """
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (table,))
            row = cur.fetchone()
    if not row or not row[2]:
        return []
    return [str(v) for v in row[2]]


def normalize_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        import pandas as pd
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def fetch_all(query: Any, params: Optional[Sequence[Any]] = None) -> List[Dict[str, Any]]:
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            return [dict(row) for row in cur.fetchall()]


def fetch_one(query: Any, params: Optional[Sequence[Any]] = None) -> Optional[Dict[str, Any]]:
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
    return dict(row) if row is not None else None


def healthcheck() -> Dict[str, Any]:
    row = fetch_one(
        """
        SELECT
            current_database() AS database_name,
            current_user AS database_user,
            version() AS postgres_version
        """
    )
    if row is None:
        raise RuntimeError("PostgreSQL n'a retourné aucune information.")
    return {
        "ok": True,
        "database": row.get("database_name"),
        "user": row.get("database_user"),
        "version": row.get("postgres_version"),
        "tables": len(list_tables()),
    }
