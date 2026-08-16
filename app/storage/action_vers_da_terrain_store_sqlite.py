from __future__ import annotations

from app.storage._queue_store_common import ensure_queue_table, fill_queue_from_clients_campagnes

QUEUE_TABLE = "vers_da_terrain"


def ensure_vers_da_terrain_table() -> None:
    ensure_queue_table(QUEUE_TABLE)


def fill_action_vers_da_terrain_from_clients_campagnes(id_campagne: str) -> int:
    return fill_queue_from_clients_campagnes(QUEUE_TABLE, id_campagne, "Directeur d'agence")
