from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from psycopg import Connection
from psycopg.rows import dict_row

from app.storage.postgres_db import get_connection


# Colonnes historiques créées avec une casse explicite dans PostgreSQL.
# Elles doivent être quotées dans les requêtes SQL.
_LEGACY_QUOTED_IDENTIFIERS = (
    "Activation_du_compte",
    "Compte_MAD_convertible_active",
    "Compte_CIH_Mobile_active",
    "Volume_transaction_inter",
    "Nombre_transaction_inter",
    "Carte_virtuelle_active",
    "Resultat_last_action",
    "NB_approche_commercial",
    "NB_da",
    "NB_cc",
    "NB_push",
    "Compte_MAD_convertible",
    "Validation_KYC",
    "Dotation_touristique",
    "Segment_actuel",
    "Dossier_Complet",
    "Canal_acquisition",
    "Assurance_Actuelle",
    "Carte_Actuelle",
    "Date_last_action",
    "NB_jour_last_action",
    "NB_jour_campagne",
    "Compte_CIH_Mobile",
    "Activation_carte",
    "Eligible_credit",
    "Carte_virtuelle",
    "Premiere_connex",
    "Dotation_ecom",
    "STATUT_CLIENT",
    "Radical_compte",
    "ID_CAMPAGNE",
    "Nom_campagne",
    "Etat_campagne",
    "ID_Action",
    "Last_action",
    "Numero_Tel",
    "ID_Client",
    "ID_CIBLE",
    "Gestionnaire",
    "Anciennete",
    "Qualite",
    "Region",
    "Agence",
    "Prenom",
    "Nom",
    "Mail",
    "Canal",
    "Action",
    "NB_appel",
    "NB_mail",
    "NB_sms",
    "NB_message",
    "visitMode",
    "visitPurpose",
)


def _prepare_sql(query: str) -> str:
    """
    Convertit le SQL historique SQLite encore présent dans les couches
    runtime vers la syntaxe psycopg/PostgreSQL.

    Cette couche est transitoire : elle permet de migrer le runtime sans
    modifier la logique métier en même temps. Les requêtes pourront ensuite
    être normalisées module par module.
    """
    prepared = str(query)

    # SQLite rowid n'existe pas sous PostgreSQL. La table
    # clients_campagnes possède maintenant une vraie PK technique `id`.
    prepared = re.sub(r"\browid\b", "id", prepared, flags=re.IGNORECASE)

    # Placeholders DB-API SQLite -> psycopg.
    prepared = prepared.replace("?", "%s")

    # Quote uniquement les identifiants historiques à casse mixte.
    for name in _LEGACY_QUOTED_IDENTIFIERS:
        pattern = rf'(?<!["\'\w]){re.escape(name)}(?!["\'\w])'
        prepared = re.sub(
            pattern,
            f'"{name}"',
            prepared,
        )

    return prepared


class HybridRow(dict):
    """Dict compatible avec les accès SQLite historiques par index."""
    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def _hybridize(row: Any) -> Any:
    if isinstance(row, dict) and not isinstance(row, HybridRow):
        return HybridRow(row)
    return row


class RuntimeCursor:
    def __init__(self, cursor: Any):
        self._cursor = cursor

    def execute(
        self,
        query: Any,
        params: Optional[Iterable[Any]] = None,
    ) -> "RuntimeCursor":
        if isinstance(query, str):
            query = _prepare_sql(query)

        self._cursor.execute(
            query,
            tuple(params) if params is not None else None,
        )
        return self

    def executemany(
        self,
        query: Any,
        params_seq: Iterable[Iterable[Any]],
    ) -> "RuntimeCursor":
        if isinstance(query, str):
            query = _prepare_sql(query)

        self._cursor.executemany(
            query,
            [tuple(params) for params in params_seq],
        )
        return self

    def fetchone(self) -> Any:
        return _hybridize(self._cursor.fetchone())

    def fetchall(self) -> Any:
        return [_hybridize(row) for row in self._cursor.fetchall()]

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def description(self) -> Any:
        return self._cursor.description

    def __iter__(self):
        return iter(self._cursor)

    def __enter__(self) -> "RuntimeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._cursor.close()

    def close(self) -> None:
        self._cursor.close()


class RuntimeConnection:
    """
    Petit adaptateur autour de psycopg utilisé pendant la migration du runtime.

    - lignes renvoyées sous forme de dict ;
    - placeholders SQLite traduits vers psycopg ;
    - colonnes historiques à casse mixte correctement quotées ;
    - `rowid` historique de clients_campagnes redirigé vers sa PK `id`.
    """

    def __init__(self) -> None:
        self._conn: Connection = get_connection(dict_rows=True)

    def cursor(self, *args: Any, **kwargs: Any) -> RuntimeCursor:
        return RuntimeCursor(
            self._conn.cursor(*args, **kwargs)
        )

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "RuntimeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()


def connect_runtime() -> RuntimeConnection:
    return RuntimeConnection()


def read_dataframe(
    query: str,
    params: Optional[Iterable[Any]] = None,
):
    """
    Exécute une requête runtime avec la compatibilité SQL PostgreSQL
    puis retourne un DataFrame Pandas.
    """
    import pandas as pd

    conn = connect_runtime()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()

        if cur.description is None:
            return pd.DataFrame()

        columns = [
            desc.name
            for desc in cur.description
        ]
        return pd.DataFrame(
            rows,
            columns=columns,
        )
    finally:
        conn.close()
