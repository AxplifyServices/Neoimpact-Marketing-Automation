from __future__ import annotations

from app.data_sources.contracts import DataSourceAdapter
from app.data_sources.external_postgres import ExternalPostgresDataSource
from app.data_sources.internal_postgres import InternalPostgresDataSource
from app.storage.data_sources_store import get_data_source_config

_INTERNAL = InternalPostgresDataSource()


def get_data_source(code: str | None = None) -> DataSourceAdapter:
    source_code = str(code or "internal").strip() or "internal"
    if source_code == "internal":
        return _INTERNAL

    definition = get_data_source_config(source_code)
    if not definition:
        raise ValueError(f"Data source inconnue : {source_code}")
    if not bool(definition.get("enabled")):
        raise RuntimeError(f"Data source désactivée : {source_code}")

    kind = str(definition.get("kind") or "").strip().upper()
    if kind == "EXTERNAL_POSTGRES":
        return ExternalPostgresDataSource(definition)
    if kind == "INTERNAL_POSTGRES":
        # Une seconde définition interne n'est pas utile : le moteur interne
        # est volontairement singleton pour préserver le chemin historique.
        return _INTERNAL
    raise RuntimeError(f"Type de data source non supporté : {kind}")
