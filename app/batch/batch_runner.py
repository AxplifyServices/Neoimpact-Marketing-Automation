from __future__ import annotations

import logging
from typing import Any, Dict

from app.batch.batch_manuel import run_batch_manuel
from app.storage.postgres_db import get_connection

logger = logging.getLogger(__name__)

# Verrou PostgreSQL session-level dédié au batch.
# Il empêche deux exécutions concurrentes (manuel + automatique, ou deux schedulers).
BATCH_ADVISORY_LOCK_KEY = 2_026_081_604


class BatchAlreadyRunningError(RuntimeError):
    """Levée lorsqu'une autre exécution du batch détient déjà le verrou global."""


def run_batch_with_lock(*, trigger: str) -> Dict[str, Any]:
    """
    Exécute le batch métier sous verrou PostgreSQL global.

    Le verrou est porté par une connexion dédiée et reste actif pendant toute
    l'exécution de ``run_batch_manuel()``. Il protège notamment contre :
    - un clic manuel pendant le batch quotidien ;
    - deux lancements manuels simultanés ;
    - plusieurs instances API qui déclencheraient le scheduler au même moment.
    """
    normalized_trigger = str(trigger or "unknown").strip() or "unknown"

    lock_conn = get_connection(autocommit=True)
    lock_acquired = False

    try:
        with lock_conn.cursor() as cur:
            cur.execute(
                "SELECT pg_try_advisory_lock(%s)",
                (BATCH_ADVISORY_LOCK_KEY,),
            )
            row = cur.fetchone()
            lock_acquired = bool(row and row[0])

        if not lock_acquired:
            raise BatchAlreadyRunningError(
                "Une autre exécution du batch est déjà en cours."
            )

        logger.info("Démarrage du batch (%s).", normalized_trigger)
        result = run_batch_manuel()
        logger.info("Batch terminé avec succès (%s).", normalized_trigger)

        return {
            "trigger": normalized_trigger,
            "result": result,
        }

    except Exception:
        logger.exception("Échec du batch (%s).", normalized_trigger)
        raise

    finally:
        if lock_acquired:
            try:
                with lock_conn.cursor() as cur:
                    cur.execute(
                        "SELECT pg_advisory_unlock(%s)",
                        (BATCH_ADVISORY_LOCK_KEY,),
                    )
            except Exception:
                logger.exception("Impossible de libérer le verrou global du batch.")

        lock_conn.close()
