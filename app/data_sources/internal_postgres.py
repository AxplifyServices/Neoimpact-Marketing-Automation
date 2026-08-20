from __future__ import annotations

from typing import Any, Dict, Iterator, List

from psycopg import sql

from app.data_sources.contracts import DataSourceAdapter, TargetPreview
from app.storage.postgres_db import connection, healthcheck as internal_healthcheck


class InternalPostgresDataSource(DataSourceAdapter):
    code = "internal"
    kind = "INTERNAL_POSTGRES"

    def healthcheck(self) -> Dict[str, Any]:
        result = internal_healthcheck()
        return {"ok": bool(result.get("ok")), "code": self.code, "kind": self.kind}

    @staticmethod
    def _build(cible: Dict[str, Any], exclude_rupture_relation: bool):
        # Import tardif : évite une dépendance circulaire pendant la migration
        # progressive de l'ancien store de cibles.
        from app.storage.cibles_store_sqlite import build_db_cible_radicals_query

        built = build_db_cible_radicals_query(
            str(cible.get("id_cible") or ""),
            exclude_rupture_relation=exclude_rupture_relation,
        )
        if built is None:
            raise ValueError("La cible n'est pas exécutable sur la source PostgreSQL interne.")
        return built

    def count_target(self, cible: Dict[str, Any], *, exclude_rupture_relation: bool = False) -> int:
        query, params = self._build(cible, exclude_rupture_relation)
        count_query = sql.SQL("SELECT COUNT(*) FROM ({target}) AS target").format(target=query)
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(count_query, params or [])
                row = cur.fetchone()
        return int(row[0] or 0) if row else 0

    def preview_target(self, cible: Dict[str, Any], *, limit: int = 200) -> TargetPreview:
        lim = max(1, min(int(limit or 200), 2000))
        query, params = self._build(cible, False)
        with connection() as conn:
            with conn.cursor() as cur:
                count_query = sql.SQL("SELECT COUNT(*) FROM ({target}) AS target").format(target=query)
                cur.execute(count_query, params or [])
                row = cur.fetchone()
                total = int(row[0] or 0) if row else 0

                # Une preview interne renvoie les données clients complètes,
                # mais uniquement sur le petit LIMIT demandé.
                cur.execute(
                    sql.SQL(
                        """
                        SELECT c.*
                        FROM clients AS c
                        JOIN ({target}) AS t
                          ON t."Radical_compte" = c.radical_compte
                        LIMIT %s
                        """
                    ).format(target=query),
                    [*(params or []), lim],
                )
                columns = [desc.name for desc in (cur.description or [])]
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]
        return TargetPreview(rows=rows, total=total)

    def stream_target_keys(
        self,
        cible: Dict[str, Any],
        *,
        batch_size: int = 2000,
        exclude_rupture_relation: bool = False,
    ) -> Iterator[List[str]]:
        size = max(100, min(int(batch_size or 2000), 20000))
        query, params = self._build(cible, exclude_rupture_relation)
        with connection() as conn:
            # Curseur serveur : PostgreSQL ne renvoie jamais toute la cible au processus Python.
            with conn.cursor(name="internal_target_stream") as cur:
                cur.execute(query, params or [])
                while True:
                    rows = cur.fetchmany(size)
                    if not rows:
                        break
                    batch = [str(row[0]).strip() for row in rows if row and str(row[0] or "").strip()]
                    if batch:
                        yield batch
