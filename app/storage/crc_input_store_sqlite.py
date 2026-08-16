from __future__ import annotations

from app.storage._queue_store_common import clear_queue, ensure_queue_table, fill_queue_from_clients_campagnes

TABLE_NAME = "crc_input"


def ensure_crc_input_table() -> None:
    ensure_queue_table(TABLE_NAME)


def clear_crc_input() -> None:
    clear_queue(TABLE_NAME)


def fill_crc_input_from_clients_campagnes(id_campagne: str) -> int:
    return fill_queue_from_clients_campagnes(TABLE_NAME, id_campagne, "Appeler")
