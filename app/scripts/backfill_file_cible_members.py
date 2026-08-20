from __future__ import annotations

import os

from app.data_pipeline.file_clients import materialize_file_members
from app.storage.postgres_db import connection


def main() -> None:
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id_cible, c.chemin,
                       COUNT(cc."Radical_compte") AS existing_members
                FROM cibles AS c
                LEFT JOIN clients_cibles AS cc ON cc."ID_CIBLE" = c.id_cible
                WHERE c.source = 'Fichier plat'
                GROUP BY c.id_cible, c.chemin
                ORDER BY c.id_cible
                """
            )
            rows = [dict(row) for row in cur.fetchall()]

    total_added = 0
    for row in rows:
        cible_id = str(row.get("id_cible") or "").strip()
        path = str(row.get("chemin") or "").strip()
        existing = int(row.get("existing_members") or 0)
        if not cible_id:
            continue
        if existing > 0:
            print(f"[SKIP] {cible_id}: {existing} membres déjà matérialisés")
            continue
        if not path or not os.path.exists(path):
            print(f"[WARN] {cible_id}: fichier introuvable: {path}")
            continue
        added = materialize_file_members(cible_id, path)
        total_added += int(added)
        print(f"[OK] {cible_id}: {added} membres matérialisés")

    print(f"[DONE] membres ajoutés: {total_added}")


if __name__ == "__main__":
    main()
