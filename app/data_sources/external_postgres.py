from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterator, List

import psycopg
from psycopg import sql

from app.data_sources.contracts import DataSourceAdapter, TargetPreview
from app.data_sources.postgres_filter import build_standard_where


class ExternalPostgresDataSource(DataSourceAdapter):
    kind = "EXTERNAL_POSTGRES"

    def __init__(self, definition: Dict[str, Any]):
        self.definition = dict(definition)
        self.code = str(definition.get("code") or "").strip()
        config = definition.get("config") or {}
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except Exception:
                config = {}
        self.config: Dict[str, Any] = dict(config)
        self.secret_ref = str(definition.get("secret_ref") or "").strip()
        if not self.code:
            raise ValueError("Code de data source externe manquant.")
        if not self.secret_ref.startswith("DATASOURCE_"):
            raise ValueError(
                "Pour des raisons de sécurité, secret_ref d'une source externe doit commencer par DATASOURCE_."
            )

    def _conninfo(self) -> str:
        value = str(os.getenv(self.secret_ref) or "").strip()
        if not value:
            raise RuntimeError(f"Secret de connexion absent : {self.secret_ref}")
        return value

    def _connect(self):
        timeout = max(1, min(int(self.config.get("connect_timeout_s") or 5), 30))
        conn = psycopg.connect(self._conninfo(), connect_timeout=timeout, autocommit=True)
        statement_timeout = max(1000, min(int(self.config.get("statement_timeout_ms") or 30000), 300000))
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('statement_timeout', %s, false)", (str(statement_timeout),))
            cur.execute("SET default_transaction_read_only = on")
        return conn

    def _schema_table(self) -> tuple[str, str]:
        return (
            str(self.config.get("clients_schema") or "public").strip(),
            str(self.config.get("clients_table") or "clients").strip(),
        )

    def _columns(self, conn) -> List[str]:
        schema, table = self._schema_table()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
                """,
                (schema, table),
            )
            return [str(row[0]) for row in cur.fetchall()]

    def _target_query(self, conn, cible: Dict[str, Any], exclude_rupture_relation: bool):
        schema, table = self._schema_table()
        columns = self._columns(conn)
        raw_filter = cible.get("filtre") or {}
        if isinstance(raw_filter, str):
            try:
                raw_filter = json.loads(raw_filter)
            except Exception:
                raw_filter = {}
        field_mapping = self.config.get("field_mapping") or {}
        where, params, objective_ids, _ = build_standard_where(
            raw_filter if isinstance(raw_filter, dict) else {},
            columns=columns,
            field_mapping=field_mapping if isinstance(field_mapping, dict) else {},
        )
        if objective_ids:
            raise RuntimeError(
                "Les filtres basés sur les conversions d'anciennes campagnes nécessitent un ResultSink externe "
                "ou un moteur d'intersection. Ils ne sont pas encore activés pour les datamarts externes."
            )

        lookup = {str(column).lower(): str(column) for column in columns}
        key_requested = str(self.config.get("key_column") or "radical_compte")
        key_column = lookup.get(key_requested.lower())
        if not key_column:
            raise RuntimeError(f"Colonne clé externe introuvable : {key_requested}")

        if exclude_rupture_relation:
            status_requested = str(self.config.get("rupture_status_column") or "STATUT_CLIENT")
            status_column = lookup.get(status_requested.lower())
            if status_column:
                where.append(
                    sql.SQL("LOWER(TRIM(COALESCE(c.{field}::text, ''))) <> LOWER(%s)").format(
                        field=sql.Identifier(status_column)
                    )
                )
                params.append(str(self.config.get("rupture_status_value") or "Rupture de relation"))

        base = sql.SQL("SELECT c.{key} AS client_key FROM {schema}.{table} AS c").format(
            key=sql.Identifier(key_column),
            schema=sql.Identifier(schema),
            table=sql.Identifier(table),
        )
        if where:
            base += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where)
        return base, params, schema, table, key_column

    def healthcheck(self) -> Dict[str, Any]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                ok = bool(cur.fetchone())
            return {"ok": ok, "code": self.code, "kind": self.kind}
        finally:
            conn.close()

    def count_target(self, cible: Dict[str, Any], *, exclude_rupture_relation: bool = False) -> int:
        conn = self._connect()
        try:
            target, params, _, _, _ = self._target_query(conn, cible, exclude_rupture_relation)
            with conn.cursor() as cur:
                cur.execute(sql.SQL("SELECT COUNT(*) FROM ({target}) AS target").format(target=target), params)
                row = cur.fetchone()
                return int(row[0] or 0) if row else 0
        finally:
            conn.close()

    def preview_target(self, cible: Dict[str, Any], *, limit: int = 200) -> TargetPreview:
        lim = max(1, min(int(limit or 200), 2000))
        conn = self._connect()
        try:
            target, params, schema, table, key_column = self._target_query(conn, cible, False)
            with conn.cursor() as cur:
                cur.execute(sql.SQL("SELECT COUNT(*) FROM ({target}) AS target").format(target=target), params)
                row = cur.fetchone()
                total = int(row[0] or 0) if row else 0
                cur.execute(
                    sql.SQL(
                        """
                        SELECT c.*
                        FROM {schema}.{table} AS c
                        JOIN ({target}) AS t ON t.client_key = c.{key}
                        LIMIT %s
                        """
                    ).format(
                        schema=sql.Identifier(schema),
                        table=sql.Identifier(table),
                        target=target,
                        key=sql.Identifier(key_column),
                    ),
                    [*params, lim],
                )
                columns = [desc.name for desc in (cur.description or [])]
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]
            return TargetPreview(rows=rows, total=total)
        finally:
            conn.close()

    def stream_target_keys(
        self,
        cible: Dict[str, Any],
        *,
        batch_size: int = 2000,
        exclude_rupture_relation: bool = False,
    ) -> Iterator[List[str]]:
        size = max(100, min(int(batch_size or 2000), 20000))
        # Le curseur serveur nécessite une transaction, donc connexion dédiée
        # en autocommit=False uniquement pendant le stream.
        timeout = max(1, min(int(self.config.get("connect_timeout_s") or 5), 30))
        conn = psycopg.connect(self._conninfo(), connect_timeout=timeout, autocommit=False)
        try:
            statement_timeout = max(1000, min(int(self.config.get("statement_timeout_ms") or 30000), 300000))
            with conn.cursor() as setup_cur:
                setup_cur.execute("SET TRANSACTION READ ONLY")
                setup_cur.execute("SELECT set_config('statement_timeout', %s, true)", (str(statement_timeout),))
            target, params, _, _, _ = self._target_query(conn, cible, exclude_rupture_relation)
            with conn.cursor(name=f"target_{self.code[:24]}") as cur:
                cur.execute(target, params)
                while True:
                    rows = cur.fetchmany(size)
                    if not rows:
                        break
                    batch = [str(row[0]).strip() for row in rows if row and str(row[0] or "").strip()]
                    if batch:
                        yield batch
        finally:
            conn.rollback()
            conn.close()
