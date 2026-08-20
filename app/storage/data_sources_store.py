from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.storage.postgres_db import connection, table_exists

TABLE = "data_sources"


def ensure_table() -> None:
    if not table_exists(TABLE):
        raise RuntimeError(
            "La table PostgreSQL 'data_sources' est absente. "
            "Appliquez database/init/008_orchestration_data_sources.sql."
        )


def get_data_source_config(code: str) -> Optional[Dict[str, Any]]:
    ensure_table()
    source_code = str(code or "internal").strip() or "internal"
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT code, name, kind, enabled, read_only, config, secret_ref
                FROM data_sources
                WHERE code = %s
                """,
                (source_code,),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def list_enabled_data_sources() -> List[Dict[str, Any]]:
    ensure_table()
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT code, name, kind, enabled, read_only, config
                FROM data_sources
                WHERE enabled = TRUE
                ORDER BY name, code
                """
            )
            rows = cur.fetchall()
    return [dict(row) for row in rows]
