from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional

from app.storage.postgres_db import connection, ensure_table_columns

TABLE_NAME = "campagnes"

_EXPECTED_COLUMNS = {
    "id_campagne",
    "nom_campagne",
    "id_modele",
    "id_cible",
    "date_creation",
    "date_debut",
    "date_fin",
    "etat_campagne",
    "description",
    "type_campagne",
    "visitMode",
    "visitPurpose",
    "data_source_code",
    "execution_status",
    "execution_error",
    "preparation_started_at",
    "preparation_finished_at",
    "target_count_initial",
    "target_count_eligible",
    "population_count",
}


def ensure_table() -> None:
    ensure_table_columns(TABLE_NAME, _EXPECTED_COLUMNS)


def _new_id_campagne(cur) -> str:
    cur.execute(
        """
        SELECT id_campagne
        FROM campagnes
        WHERE id_campagne ~ '^CP[0-9]+$'
        ORDER BY CAST(SUBSTRING(id_campagne FROM 3) AS BIGINT) DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return "CP000001"
    match = re.search(r"(\d+)$", str(row[0]))
    number = int(match.group(1)) if match else 0
    return f"CP{number + 1:06d}"


def insert_campagne(
    *,
    nom_campagne: str,
    id_modele: str,
    id_cible: str,
    date_debut: str,
    date_fin: str,
    etat_campagne: str,
    description: Optional[str] = None,
    type_campagne: str = "sans_action_terrain",
    visitMode: Optional[str] = None,
    visitPurpose: Optional[str] = None,
    execution_status: str = "ready",
    enqueue_prepare_job: bool = False,
) -> str:
    ensure_table()
    today = date.today().isoformat()

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (620010,))
            id_campagne = _new_id_campagne(cur)
            cur.execute("SELECT data_source_code FROM cibles WHERE id_cible = %s", (str(id_cible),))
            source_row = cur.fetchone()
            data_source_code = str(source_row[0] if source_row and source_row[0] else "internal")
            cur.execute(
                """
                INSERT INTO campagnes (
                    id_campagne,
                    nom_campagne,
                    id_modele,
                    id_cible,
                    date_debut,
                    date_fin,
                    etat_campagne,
                    date_creation,
                    description,
                    type_campagne,
                    "visitMode",
                    "visitPurpose",
                    data_source_code,
                    execution_status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    id_campagne,
                    (nom_campagne or "").strip(),
                    str(id_modele),
                    str(id_cible),
                    str(date_debut),
                    str(date_fin),
                    str(etat_campagne),
                    today,
                    None if description is None else (description or "").strip(),
                    str(type_campagne or "sans_action_terrain").strip(),
                    visitMode,
                    visitPurpose,
                    data_source_code,
                    str(execution_status or "ready").strip() or "ready",
                ),
            )
            if enqueue_prepare_job:
                cur.execute(
                    """
                    INSERT INTO orchestration_jobs (
                        job_key, job_type, priority, status, id_campagne, payload,
                        attempts, max_attempts, available_at, updated_at
                    )
                    VALUES (%s, 'CAMPAIGN_PREPARE', 10, 'pending', %s, '{}'::jsonb,
                            0, 3, NOW(), NOW())
                    """,
                    (f"campaign_prepare:{id_campagne}", id_campagne),
                )
    return id_campagne



def set_execution_status(
    id_campagne: str,
    status: str,
    *,
    error: Optional[str] = None,
    started: bool = False,
    finished: bool = False,
    target_count_initial: Optional[int] = None,
    target_count_eligible: Optional[int] = None,
    population_count: Optional[int] = None,
) -> None:
    """Met à jour l'état technique backend d'une campagne sans toucher à son état métier."""
    ensure_table()
    assignments = ["execution_status = %s", "execution_error = %s"]
    params: List[Any] = [str(status), None if error is None else str(error)[:4000]]
    if started:
        assignments.append("preparation_started_at = NOW()")
        assignments.append("preparation_finished_at = NULL")
    if finished:
        assignments.append("preparation_finished_at = NOW()")
    if target_count_initial is not None:
        assignments.append("target_count_initial = %s")
        params.append(max(0, int(target_count_initial)))
    if target_count_eligible is not None:
        assignments.append("target_count_eligible = %s")
        params.append(max(0, int(target_count_eligible)))
    if population_count is not None:
        assignments.append("population_count = %s")
        params.append(max(0, int(population_count)))
    params.append(str(id_campagne))
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE campagnes SET {', '.join(assignments)} WHERE id_campagne = %s",
                params,
            )


def get_execution_status(id_campagne: str) -> Optional[Dict[str, Any]]:
    ensure_table()
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT execution_status, execution_error, preparation_started_at,
                       preparation_finished_at, target_count_initial,
                       target_count_eligible, population_count
                FROM campagnes
                WHERE id_campagne = %s
                """,
                (str(id_campagne),),
            )
            row = cur.fetchone()
    return dict(row) if row else None

def update_etat_campagne(id_campagne: str, new_etat: str) -> None:
    ensure_table()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE campagnes SET etat_campagne = %s WHERE id_campagne = %s",
                (new_etat, id_campagne),
            )


def update_etat(id_campagne: str, new_etat: str) -> None:
    update_etat_campagne(id_campagne, new_etat)


def _compat_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    out = dict(row)
    # Compatibilité transitoire avec les anciens consommateurs.
    if "etat_campagne" in out:
        out.setdefault("Etat_campagne", out.get("etat_campagne"))
    return out


def get_campagne(id_campagne: str) -> Optional[Dict[str, Any]]:
    ensure_table()
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM campagnes WHERE id_campagne = %s", (id_campagne,))
            row = cur.fetchone()
    return _compat_row(dict(row) if row else None)


def list_all_campagnes() -> List[Dict[str, Any]]:
    ensure_table()
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM campagnes ORDER BY date_creation DESC")
            rows = cur.fetchall()
    return [_compat_row(dict(row)) or {} for row in rows]


def list_campagnes_active() -> List[Dict[str, Any]]:
    ensure_table()
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM campagnes
                WHERE etat_campagne IN ('En cours', 'Planifiée')
                ORDER BY date_debut DESC
                """
            )
            rows = cur.fetchall()
    return [_compat_row(dict(row)) or {} for row in rows]
