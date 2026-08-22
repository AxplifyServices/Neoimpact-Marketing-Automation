from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from app.storage.runtime_db import RuntimeConnection
from app.best_channel.history import finalize_current_sequence

CLIENTS_CAMPAGNES_TABLE = "clients_campagnes"


def _norm_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def is_converted(row: Dict[str, Any]) -> bool:
    try:
        return int(row.get("conversion") or 0) == 1
    except Exception:
        return False


def record_objective_entry(
    conn: RuntimeConnection,
    rid: int,
    *,
    source_id_action: str,
    source_canal: str,
) -> None:
    """
    Mémorise le bloc/canal qui a conduit le client vers un bloc Objectif.

    Ces informations restent transitoires tant que conversion=0 et sont figées
    dans conversion_* au premier objectif atteint.
    """
    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE {CLIENTS_CAMPAGNES_TABLE}
        SET
            objective_source_id_action = ?,
            objective_source_canal = ?
        WHERE rowid = ?
          AND COALESCE(conversion, 0) <> 1
        """,
        (
            _norm_str(source_id_action),
            _norm_str(source_canal),
            int(rid),
        ),
    )


def mark_converted(
    conn: RuntimeConnection,
    rid: int,
    *,
    objective_id_action: str,
) -> bool:
    """
    Fige la première conversion d'un client.

    Règles métier :
    - conversion ne revient jamais à 0 ;
    - la première date / objectif / canal de conversion sont immuables ;
    - le client ne doit plus être remis à échéance après conversion.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE {CLIENTS_CAMPAGNES_TABLE}
        SET
            conversion = 1,
            conversion_date = CASE
                WHEN COALESCE(conversion_date, '') = '' THEN ?
                ELSE conversion_date
            END,
            conversion_id_action = CASE
                WHEN COALESCE(conversion_id_action, '') = '' THEN ?
                ELSE conversion_id_action
            END,
            conversion_canal = CASE
                WHEN COALESCE(conversion_canal, '') = '' THEN
                    COALESCE(NULLIF(objective_source_canal, ''), 'Objectif')
                ELSE conversion_canal
            END,
            arriv_eche = 'Non'
        WHERE rowid = ?
          AND COALESCE(conversion, 0) <> 1
        """,
        (
            now,
            _norm_str(objective_id_action),
            int(rid),
        ),
    )
    converted_now = int(cur.rowcount or 0) > 0
    if converted_now:
        finalize_current_sequence(
            conn,
            int(rid),
            objective_validated=1,
            objective_id_action=_norm_str(objective_id_action),
        )
        try:
            from app.product_scoring.feedback import record_objective_feedback
            record_objective_feedback(
                conn, int(rid), objective_id_action=_norm_str(objective_id_action), achieved=1
            )
        except Exception:
            pass
    return converted_now
