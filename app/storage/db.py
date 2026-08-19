from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from psycopg import IntegrityError, sql

from app.storage.postgres_db import (
    connection,
    get_connection,
    get_database_url,
    get_row_identity_columns,
    get_table_columns as _pg_get_table_columns,
    list_tables as _pg_list_tables,
    normalize_value,
)

# Compatibilité temporaire avec les modules hors storage qui importent encore DB_PATH.
# Le dossier storage n'utilise plus SQLite. Cette constante sera supprimée quand les
# derniers modules externes auront été migrés.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.environ.get("MA_DB_PATH", os.path.join(PROJECT_ROOT, "database.db"))
DATABASE_URL = get_database_url()


@dataclass
class NumericBounds:
    min: Optional[float] = None
    max: Optional[float] = None


@dataclass
class ColumnFilter:
    numeric: Optional[NumericBounds] = None
    categorical: Optional[List[str]] = None


def _to_float_or_none(value: Any) -> Optional[float]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return float(value)
    except Exception:
        return None


def list_tables() -> List[str]:
    return _pg_list_tables()


def get_table_columns(table: str) -> List[Tuple[str, str]]:
    return _pg_get_table_columns(table)


def _validate_table_column(table: str, column: Optional[str] = None) -> None:
    tables = set(list_tables())
    if table not in tables:
        raise ValueError(f"Table inconnue : {table}")
    if column is not None:
        columns = {name for name, _ in get_table_columns(table)}
        if column not in columns:
            raise ValueError(f"Colonne inconnue : {table}.{column}")


def get_distinct_values(table: str, col: str, limit: int = 200) -> List[str]:
    _validate_table_column(table, col)
    query = sql.SQL(
        "SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL LIMIT %s"
    ).format(col=sql.Identifier(col), table=sql.Identifier(table))
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (int(limit),))
            rows = cur.fetchall()
    return sorted({str(row[0]) for row in rows if row and row[0] is not None})


# Token -> (table, [(pk_col, original_value), ...])
_ROW_IDENTITY_CACHE: Dict[int, Tuple[str, List[Tuple[str, Any]]]] = {}
_ROW_IDENTITY_CACHE_MAX = 100_000


def _row_token(table: str, identity: List[Tuple[str, Any]]) -> int:
    raw = json.dumps([table, identity], ensure_ascii=False, default=str, separators=(",", ":"))
    digest = hashlib.blake2b(raw.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") & ((1 << 63) - 1)


def _remember_identity(token: int, table: str, identity: List[Tuple[str, Any]]) -> None:
    if len(_ROW_IDENTITY_CACHE) >= _ROW_IDENTITY_CACHE_MAX:
        _ROW_IDENTITY_CACHE.clear()
    _ROW_IDENTITY_CACHE[token] = (table, identity)


def read_table(
    table: str,
    filters: Optional[Dict[str, ColumnFilter]] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> pd.DataFrame:
    _validate_table_column(table)
    columns = [name for name, _ in get_table_columns(table)]
    identity_columns = get_row_identity_columns(table)
    if not identity_columns:
        raise RuntimeError(
            f"La table '{table}' n'a ni clé primaire ni index UNIQUE utilisable pour l'édition."
        )

    where_parts: List[Any] = []
    params: List[Any] = []

    if filters:
        for col, filt in filters.items():
            if filt is None:
                continue
            _validate_table_column(table, col)
            col_id = sql.Identifier(col)
            if filt.numeric is not None:
                mn = _to_float_or_none(filt.numeric.min)
                mx = _to_float_or_none(filt.numeric.max)
                if mn is not None:
                    where_parts.append(sql.SQL("CAST({} AS DOUBLE PRECISION) >= %s").format(col_id))
                    params.append(mn)
                if mx is not None:
                    where_parts.append(sql.SQL("CAST({} AS DOUBLE PRECISION) <= %s").format(col_id))
                    params.append(mx)
            if filt.categorical:
                values = [str(x) for x in filt.categorical]
                placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in values)
                where_parts.append(
                    sql.SQL("CAST({} AS TEXT) IN ({})").format(col_id, placeholders)
                )
                params.extend(values)

    query = sql.SQL("SELECT * FROM {}").format(sql.Identifier(table))
    if where_parts:
        query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where_parts)
    if limit is not None:
        query += sql.SQL(" LIMIT %s OFFSET %s")
        params.extend([int(limit), int(offset)])

    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = [dict(row) for row in cur.fetchall()]

    output: List[Dict[str, Any]] = []
    for row in rows:
        identity = [(name, row.get(name)) for name in identity_columns]
        token = _row_token(table, identity)
        _remember_identity(token, table, identity)
        output.append({"__rowid__": token, **row})

    return pd.DataFrame(output, columns=["__rowid__", *columns])



def count_table(
    table: str,
    filters: Optional[Dict[str, ColumnFilter]] = None,
) -> int:
    """Compte les lignes avec les mêmes filtres que read_table, sans matérialiser les données."""
    _validate_table_column(table)

    where_parts: List[Any] = []
    params: List[Any] = []

    if filters:
        for col, filt in filters.items():
            if filt is None:
                continue
            _validate_table_column(table, col)
            col_id = sql.Identifier(col)

            if filt.numeric is not None:
                mn = _to_float_or_none(filt.numeric.min)
                mx = _to_float_or_none(filt.numeric.max)
                if mn is not None:
                    where_parts.append(sql.SQL("CAST({} AS DOUBLE PRECISION) >= %s").format(col_id))
                    params.append(mn)
                if mx is not None:
                    where_parts.append(sql.SQL("CAST({} AS DOUBLE PRECISION) <= %s").format(col_id))
                    params.append(mx)

            if filt.categorical:
                values = [str(x) for x in filt.categorical]
                placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in values)
                where_parts.append(
                    sql.SQL("CAST({} AS TEXT) IN ({})").format(col_id, placeholders)
                )
                params.extend(values)

    query = sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))
    if where_parts:
        query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where_parts)

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()

    return int(row[0] if row else 0)

def update_cell(table: str, rowid: int, col: str, value: Any) -> None:
    _validate_table_column(table, col)
    identity_info = _ROW_IDENTITY_CACHE.get(int(rowid))
    if identity_info is None or identity_info[0] != table:
        raise ValueError(
            "Identifiant de ligne expiré ou inconnu. Rechargez la table avant de modifier la cellule."
        )

    identity = identity_info[1]
    where_parts = []
    params: List[Any] = [normalize_value(value)]
    for pk_col, pk_value in identity:
        if pk_value is None:
            where_parts.append(sql.SQL("{} IS NULL").format(sql.Identifier(pk_col)))
        else:
            where_parts.append(sql.SQL("{} = %s").format(sql.Identifier(pk_col)))
            params.append(normalize_value(pk_value))

    query = (
        sql.SQL("UPDATE {} SET {} = %s WHERE ")
        .format(sql.Identifier(table), sql.Identifier(col))
        + sql.SQL(" AND ").join(where_parts)
    )
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if cur.rowcount != 1:
                raise RuntimeError(
                    f"Modification ambiguë ou ligne introuvable dans '{table}' (rowcount={cur.rowcount})."
                )

    # Si une colonne d'identité a changé, garde le token valide pour les autres
    # modifications du même cycle d'édition.
    for idx, (pk_col, _) in enumerate(identity):
        if pk_col == col:
            identity[idx] = (pk_col, normalize_value(value))
            break
    _ROW_IDENTITY_CACHE[int(rowid)] = (table, identity)


def insert_client_if_new(data: Dict[str, Any]) -> Tuple[bool, str]:
    required_id = str(data.get("ID_Client") or "").strip()
    if not required_id:
        return False, "ID_Client obligatoire."

    valid_columns = {name for name, _ in get_table_columns("clients")}
    clean = {key: normalize_value(value) for key, value in data.items() if key in valid_columns}
    clean["ID_Client"] = required_id
    clean.pop("radical_compte", None)

    try:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (620001,))
                cur.execute('SELECT 1 FROM clients WHERE "ID_Client" = %s LIMIT 1', (required_id,))
                if cur.fetchone():
                    return False, f"ID_Client '{required_id}' existe déjà."

                cur.execute("SELECT nextval('client_radical_seq')")
                row = cur.fetchone()
                next_num = int(row[0])
                radical = f"RC{next_num:08d}"
                clean["radical_compte"] = radical

                cols = list(clean.keys())
                query = sql.SQL("INSERT INTO clients ({}) VALUES ({})").format(
                    sql.SQL(", ").join(sql.Identifier(c) for c in cols),
                    sql.SQL(", ").join(sql.Placeholder() for _ in cols),
                )
                cur.execute(query, [clean[c] for c in cols])
        return True, f"Client créé: {radical}"
    except IntegrityError as exc:
        return False, f"Erreur insertion: {exc}"
    except Exception as exc:
        return False, f"Erreur insertion: {exc}"
