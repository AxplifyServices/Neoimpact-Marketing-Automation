from __future__ import annotations

import json
import os
import re
import shutil
import time
from typing import Any, Dict, List, Tuple

import pandas as pd
from psycopg import sql
from psycopg.rows import dict_row

from app.domain.cible import Cible
from app.data_sources import get_data_source
from app.data_pipeline.file_clients import bulk_import_clients, materialize_file_members
from app.storage.postgres_db import (
    connection,
    get_column_names,
    table_exists,
)


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
    )
)

UPLOAD_DIR = os.path.join(
    PROJECT_ROOT,
    "uploads",
    "cibles",
)

CIBLES_TABLE = "cibles"
CLIENTS_TABLE = "clients"
CLIENTS_CAMPAGNES_TABLE = "clients_campagnes"

STRICT_REQUIRED_COLS = [
    "ID_Client",
    "Numero_Tel",
    "Mail",
]

STRICT_KEY_COL = "ID_Client"
RADICAL_COL = "radical_compte"

OBJECTIF_CAMPAGNES_FILTER_KEY = "__objectif_campagnes__"


# ============================================================
# SCHEMA VALIDATION
# ============================================================

def ensure_cibles_table() -> None:
    """
    Vérifie que la table PostgreSQL cibles possède le schéma
    attendu.

    Le code applicatif ne crée plus automatiquement les tables.
    Toute modification du schéma doit passer par un fichier SQL.
    """

    if not table_exists(CIBLES_TABLE):
        raise RuntimeError(
            "La table PostgreSQL 'cibles' est absente."
        )

    columns = set(
        get_column_names(CIBLES_TABLE)
    )

    expected = {
        "id_cible",
        "nom_cible",
        "date_creation",
        "source",
        "filtre",
        "chemin",
        "data_source_code",
    }

    missing = expected - columns

    if missing:
        raise RuntimeError(
            "Schéma PostgreSQL invalide pour 'cibles'. "
            f"Colonnes absentes : {', '.join(sorted(missing))}"
        )


# ============================================================
# COUNT CLIENTS
# ============================================================

def count_clients_for_cible(
    id_cible: str,
) -> int:
    """Compte une cible sans matérialiser sa population en Python."""
    cible = get_cible(id_cible)
    if not cible:
        return 0

    if str(cible.get("source") or "").strip() == "Fichier plat":
        from app.storage.clients_cibles_store_sqlite import get_volume
        return int(get_volume(id_cible) or 0)

    source_code = str(cible.get("data_source_code") or "internal").strip() or "internal"
    try:
        adapter = get_data_source(source_code)
        return int(adapter.count_target(cible, exclude_rupture_relation=False) or 0)
    except Exception:
        # L'ancien écran tolère encore un échec de comptage interne. Pour une
        # source externe, masquer une panne datamart sous un volume=0 serait
        # dangereux : on laisse donc l'erreur remonter.
        if source_code != "internal":
            raise
        return 0


# ============================================================
# IDS
# ============================================================

def _new_id_cible(cur) -> str:
    """
    Génère :
        C000001
        C000002
        ...

    L'appelant doit être dans une transaction ayant acquis
    le verrou advisory utilisé dans insert_cible().
    """

    cur.execute(
        """
        SELECT id_cible
        FROM cibles
        WHERE id_cible ~ '^C[0-9]+$'
        ORDER BY
            CAST(
                SUBSTRING(id_cible FROM 2)
                AS BIGINT
            ) DESC
        LIMIT 1
        """
    )

    row = cur.fetchone()

    if not row:
        return "C000001"

    last = str(
        row[0] or ""
    )

    match = re.search(
        r"(\d+)$",
        last,
    )

    number = (
        int(match.group(1))
        if match
        else 0
    )

    return f"C{number + 1:06d}"


# ============================================================
# CRUD CIBLES
# ============================================================

def insert_cible(
    cible: Cible,
) -> str:
    """
    Insère une cible dans PostgreSQL.

    Si id_cible est vide, un identifiant est généré.
    """

    ensure_cibles_table()

    cible.validate()

    filtre_str = (
        json.dumps(
            cible.filtre,
            ensure_ascii=False,
        )
        if cible.source == "DB"
        else ""
    )

    chemin = (
        cible.chemin
        if cible.source == "Fichier plat"
        else ""
    )

    with connection() as conn:
        with conn.cursor() as cur:

            # Empêche deux créations simultanées de générer
            # le même C000xxx.
            cur.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (610001,),
            )

            if not cible.id_cible:
                cible.id_cible = _new_id_cible(
                    cur
                )

            cur.execute(
                """
                INSERT INTO cibles (
                    id_cible,
                    nom_cible,
                    date_creation,
                    source,
                    filtre,
                    chemin,
                    data_source_code
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    cible.id_cible,
                    cible.nom_cible,
                    cible.date_creation,
                    cible.source,
                    filtre_str,
                    chemin,
                    cible.data_source_code,
                ),
            )

    return str(
        cible.id_cible
    )


def list_cibles() -> List[Dict[str, Any]]:
    ensure_cibles_table()

    with connection(
        dict_rows=True
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM cibles
                ORDER BY date_creation DESC
                """
            )

            rows = cur.fetchall()

    return [
        dict(row)
        for row in rows
    ]


def _campagne_use_cible(
    conn,
    id_cible: str,
) -> Dict[str, Any] | None:
    """
    Retourne une campagne active ou planifiée utilisant
    la cible.

    IMPORTANT :
    la vraie colonne du schéma est etat_campagne.

    L'ancienne implémentation utilisait "etat", colonne
    inexistante, puis absorbait silencieusement l'erreur.
    """

    with conn.cursor(
        row_factory=dict_row
    ) as cur:
        cur.execute(
            """
            SELECT
                id_campagne,
                nom_campagne,
                etat_campagne
            FROM campagnes
            WHERE id_cible = %s
              AND etat_campagne IN (
                  'En cours',
                  'Planifiée'
              )
            LIMIT 1
            """,
            (
                id_cible,
            ),
        )

        row = cur.fetchone()

    if row is None:
        return None

    return {
        "id_campagne": row.get(
            "id_campagne"
        ),
        "nom_campagne": row.get(
            "nom_campagne"
        ),
        "etat": row.get(
            "etat_campagne"
        ),
    }


def delete_cible(
    id_cible: str,
) -> None:
    """
    Supprime une cible uniquement si elle n'est utilisée
    par aucune campagne En cours / Planifiée.

    Si la cible vient d'un fichier plat, le fichier associé
    est ensuite supprimé du disque.

    Les clients eux-mêmes ne sont jamais supprimés.
    """

    ensure_cibles_table()

    source = ""
    chemin = ""

    with connection(
        dict_rows=True
    ) as conn:

        used = _campagne_use_cible(
            conn,
            id_cible,
        )

        if used:
            raise ValueError(
                "Impossible de supprimer : cible utilisée "
                "par campagne active/planifiée "
                f"'{used.get('nom_campagne')}' "
                f"({used.get('etat')})."
            )

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM cibles
                WHERE id_cible = %s
                """,
                (
                    id_cible,
                ),
            )

            row = cur.fetchone()

            if row is None:
                return

            source = str(
                row.get("source") or ""
            ).strip()

            chemin = str(
                row.get("chemin") or ""
            ).strip()

            cur.execute(
                """
                DELETE FROM cibles
                WHERE id_cible = %s
                """,
                (
                    id_cible,
                ),
            )

    if (
        source == "Fichier plat"
        and chemin
        and os.path.exists(chemin)
    ):
        try:
            os.remove(
                chemin
            )
        except Exception:
            # Conservation du comportement existant :
            # une erreur filesystem ne réinjecte pas la cible
            # supprimée en base.
            pass


def get_cibles_count() -> int:
    ensure_cibles_table()

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM cibles
                """
            )

            row = cur.fetchone()

    return int(
        row[0]
        if row
        else 0
    )


def get_cible(
    id_cible: str,
) -> Dict[str, Any] | None:
    ensure_cibles_table()

    with connection(
        dict_rows=True
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM cibles
                WHERE id_cible = %s
                """,
                (
                    id_cible,
                ),
            )

            row = cur.fetchone()

    if row is None:
        return None

    return dict(
        row
    )


def update_cible(
    cible: Cible,
) -> None:
    """
    Met à jour une cible existante.
    """

    ensure_cibles_table()

    cible.validate()

    filtre_str = (
        json.dumps(
            cible.filtre,
            ensure_ascii=False,
        )
        if cible.source == "DB"
        else ""
    )

    chemin = (
        cible.chemin
        if cible.source == "Fichier plat"
        else ""
    )

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE cibles
                SET
                    nom_cible = %s,
                    date_creation = %s,
                    source = %s,
                    filtre = %s,
                    chemin = %s,
                    data_source_code = %s
                WHERE id_cible = %s
                """,
                (
                    cible.nom_cible,
                    cible.date_creation,
                    cible.source,
                    filtre_str,
                    chemin,
                    cible.data_source_code,
                    cible.id_cible,
                ),
            )


def update_nom_cible(
    id_cible: str,
    nom_cible: str,
) -> None:
    ensure_cibles_table()

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE cibles
                SET nom_cible = %s
                WHERE id_cible = %s
                """,
                (
                    nom_cible,
                    id_cible,
                ),
            )


def update_cible_chemin(
    id_cible: str,
    chemin: str,
) -> None:
    ensure_cibles_table()

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE cibles
                SET chemin = %s
                WHERE id_cible = %s
                """,
                (
                    chemin,
                    id_cible,
                ),
            )


# ============================================================
# UPLOAD FILE
# Streamlit & FastAPI
# ============================================================

def save_uploaded_file(
    uploaded_file,
) -> str:
    """
    Enregistre un fichier uploadé sur disque.

    Compatible :
    - Streamlit UploadedFile
    - FastAPI UploadFile
    """

    os.makedirs(
        UPLOAD_DIR,
        exist_ok=True,
    )

    name = (
        getattr(
            uploaded_file,
            "name",
            None,
        )
        or getattr(
            uploaded_file,
            "filename",
            None,
        )
    )

    if not name:
        name = (
            f"uploaded_file_{int(time.time())}"
        )

    base, ext = os.path.splitext(
        name
    )

    dst = os.path.join(
        UPLOAD_DIR,
        name,
    )

    index = 1

    while os.path.exists(dst):
        dst = os.path.join(
            UPLOAD_DIR,
            f"{base}_{index}{ext}",
        )

        index += 1

    with open(
        dst,
        "wb",
    ) as file_obj:

        if hasattr(
            uploaded_file,
            "getbuffer",
        ):
            file_obj.write(
                uploaded_file.getbuffer()
            )

        elif hasattr(
            uploaded_file,
            "file",
        ):
            uploaded_file.file.seek(0)

            shutil.copyfileobj(
                uploaded_file.file,
                file_obj,
            )

        else:
            data = (
                uploaded_file.read()
                if hasattr(
                    uploaded_file,
                    "read",
                )
                else None
            )

            if data:
                file_obj.write(
                    data
                )

            else:
                raise AttributeError(
                    "Impossible de lire le fichier envoyé."
                )

    return dst


# ============================================================
# FILE READING
# ============================================================

def _read_flat_file(
    path: str,
) -> pd.DataFrame:
    """
    Lecture multi-formats :
    CSV, XLSX, XLS, Parquet, JSON.
    """

    ext = (
        os.path.splitext(path)[1]
        .lower()
        .strip(".")
    )

    if ext == "csv":
        return pd.read_csv(
            path
        )

    if ext in (
        "xlsx",
        "xls",
    ):
        return pd.read_excel(
            path,
            sheet_name=0,
        )

    if ext == "parquet":
        return pd.read_parquet(
            path
        )

    if ext == "json":
        return pd.read_json(
            path
        )

    raise ValueError(
        "Type de fichier non supporté "
        "(csv/xlsx/xls/parquet/json)"
    )


# ============================================================
# POSTGRESQL TABLE INTROSPECTION
# ============================================================

def _detect_clients_table(
    conn,
) -> str:
    """
    Trouve la table clients.

    Le schéma actuel contient explicitement 'clients',
    mais le fallback historique est conservé.
    """

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )

        tables = [
            str(row[0])
            for row in cur.fetchall()
        ]

    if "clients" in tables:
        return "clients"

    for table in tables:
        lower = table.lower()

        if (
            lower == "client"
            or "client" in lower
        ):
            return table

    raise RuntimeError(
        "Table clients introuvable dans PostgreSQL."
    )


def _get_table_columns(
    conn,
    table: str,
) -> List[str]:
    """
    Équivalent PostgreSQL de PRAGMA table_info().
    """

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (
                table,
            ),
        )

        rows = cur.fetchall()

    return [
        str(row[0])
        for row in rows
    ]


def _resolve_column_name(
    columns: List[str],
    requested: str,
) -> str:
    """
    Résout une colonne en respectant la casse PostgreSQL.

    Exemple :
        ID_Client
        Radical_compte
        Nom
    """

    if requested in columns:
        return requested

    lookup = {
        str(column).lower(): str(column)
        for column in columns
    }

    resolved = lookup.get(
        str(requested).lower()
    )

    if resolved:
        return resolved

    raise ValueError(
        f"Colonne clients inconnue : {requested}"
    )


# ============================================================
# STRICT IMPORT VALIDATION
# ============================================================

def _strict_validate_dataframe_against_clients(
    df: pd.DataFrame,
    clients_cols: List[str],
) -> None:
    """
    Le fichier doit contenir EXACTEMENT les mêmes colonnes
    que la table clients.

    Colonnes obligatoires :
    - ID_Client
    - Numero_Tel
    - Mail
    """

    df_cols = [
        str(column).strip()
        for column in df.columns
    ]

    clients_cols = [
        str(column).strip()
        for column in clients_cols
    ]

    df_set = set(
        df_cols
    )

    db_set = set(
        clients_cols
    )

    missing = sorted(
        db_set - df_set
    )

    extra = sorted(
        df_set - db_set
    )

    if missing or extra:
        message = [
            "Fichier invalide (STRICT). "
            "Le schéma doit correspondre EXACTEMENT "
            "à la table clients."
        ]

        if missing:
            message.append(
                f"Colonnes manquantes ({len(missing)}) : "
                f"{', '.join(missing)}"
            )

        if extra:
            message.append(
                f"Colonnes en trop ({len(extra)}) : "
                f"{', '.join(extra)}"
            )

        raise ValueError(
            "\n".join(message)
        )

    for column in STRICT_REQUIRED_COLS:

        if column not in df_set:
            raise ValueError(
                "Fichier invalide : "
                f"colonne obligatoire manquante : {column}"
            )

        if df[column].isna().any():
            raise ValueError(
                "Fichier invalide : "
                f"la colonne '{column}' contient "
                "des valeurs vides (obligatoire)."
            )


# ============================================================
# VALUE NORMALIZATION
# ============================================================

def _to_db_value(
    value: Any,
) -> Any:
    """
    Convertit proprement les scalaires Pandas / NumPy
    avant envoi à psycopg.
    """

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if hasattr(
        value,
        "to_pydatetime",
    ):
        try:
            return value.to_pydatetime()
        except Exception:
            pass

    if hasattr(
        value,
        "item",
    ):
        try:
            return value.item()
        except Exception:
            pass

    return value


# ============================================================
# RADICAL COMPTE
# ============================================================

def _new_radical_compte(
    cur,
    clients_table: str,
) -> str:
    """
    Génère :
        RC000001
        RC000002
        ...
    """

    query = sql.SQL(
        """
        SELECT {radical}
        FROM {table}
        WHERE {radical} ~ '^RC[0-9]+$'
        ORDER BY
            CAST(
                SUBSTRING({radical} FROM 3)
                AS BIGINT
            ) DESC
        LIMIT 1
        """
    ).format(
        radical=sql.Identifier(
            RADICAL_COL
        ),
        table=sql.Identifier(
            clients_table
        ),
    )

    cur.execute(
        query
    )

    row = cur.fetchone()

    if (
        not row
        or not row[0]
    ):
        return "RC000001"

    last = str(
        row[0]
    )

    match = re.search(
        r"(\d+)$",
        last,
    )

    number = (
        int(match.group(1))
        if match
        else 0
    )

    return f"RC{number + 1:06d}"


# ============================================================
# IMPORT LEADS -> CLIENTS
# ============================================================

def import_leads_into_clients(
    file_path: str,
) -> Tuple[int, int]:
    """Import clients en streaming/COPY PostgreSQL, mémoire bornée."""
    return bulk_import_clients(file_path)


# ============================================================
# DISTINCT CLIENT VALUES
# ============================================================

def get_distinct_values_clients(
    column: str,
) -> List[str]:
    """
    Retourne les valeurs distinctes d'une colonne clients.

    Le nom de colonne est validé contre le vrai schéma avant
    d'être utilisé dans la requête.
    """

    with connection() as conn:

        clients_table = _detect_clients_table(
            conn
        )

        columns = _get_table_columns(
            conn,
            clients_table,
        )

        try:
            actual_column = _resolve_column_name(
                columns,
                column,
            )
        except ValueError:
            return []

        query = sql.SQL(
            """
            SELECT DISTINCT {column} AS v
            FROM {table}
            WHERE {column} IS NOT NULL
            ORDER BY {column}
            """
        ).format(
            column=sql.Identifier(
                actual_column
            ),
            table=sql.Identifier(
                clients_table
            ),
        )

        try:
            with conn.cursor() as cur:
                cur.execute(
                    query
                )

                rows = cur.fetchall()

        except Exception:
            return []

    return [
        str(row[0])
        for row in rows
        if (
            row[0] is not None
            and str(row[0]).strip() != ""
        )
    ]


# ============================================================
# OBJECTIF CAMPAGNE FILTER
# ============================================================

def _split_objectif_campaign_filter(
    filtre: Dict[str, Any],
) -> tuple[
    Dict[str, Any],
    List[str],
    str,
]:
    normal_filtre: Dict[
        str,
        Any,
    ] = {}

    campagne_ids: List[str] = []

    mode = "atteint"

    for key, value in (
        filtre or {}
    ).items():

        if key == OBJECTIF_CAMPAGNES_FILTER_KEY:

            if isinstance(
                value,
                dict,
            ):
                raw = (
                    value.get("values")
                    or value.get("ids")
                    or []
                )

                mode = str(
                    value.get("mode")
                    or value.get("status")
                    or "atteint"
                ).strip().lower()

            elif isinstance(
                value,
                list,
            ):
                raw = value

            else:
                raw = []

            campagne_ids = [
                str(item).strip()
                for item in raw
                if str(item).strip()
            ]

        else:
            normal_filtre[
                key
            ] = value

    if mode not in {
        "atteint",
        "non_atteint",
    }:
        mode = "atteint"

    return (
        normal_filtre,
        campagne_ids,
        mode,
    )


def _detect_radical_column(
    conn,
    table: str,
) -> str:
    columns = _get_table_columns(
        conn,
        table,
    )

    lookup = {
        str(column).lower(): str(column)
        for column in columns
    }

    if "radical_compte" in lookup:
        return lookup[
            "radical_compte"
        ]

    raise ValueError(
        "Base clients : colonne "
        "'radical_compte' manquante"
    )


# ============================================================
# QUERY CLIENTS BY FILTER
# ============================================================

def _query_clients_by_filtre(
    filtre: Dict[str, Any],
) -> pd.DataFrame:

    with connection() as conn:

        table = _detect_clients_table(
            conn
        )

        clients_columns = _get_table_columns(
            conn,
            table,
        )

        normal_filtre, objectif_campagne_ids, objectif_mode = (
            _split_objectif_campaign_filter(
                filtre or {}
            )
        )

        where_clauses = []
        params: List[Any] = []

        for field, payload in (
            normal_filtre or {}
        ).items():

            if not isinstance(
                payload,
                dict,
            ):
                continue

            actual_field = _resolve_column_name(
                clients_columns,
                field,
            )

            field_identifier = sql.Identifier(
                actual_field
            )

            if "values" in payload:

                raw_values = (
                    payload.get("values")
                    or []
                )

                values = [
                    value
                    for value in raw_values
                    if (
                        value is not None
                        and str(value).strip() != ""
                    )
                ]

                if values:
                    placeholders = sql.SQL(
                        ", "
                    ).join(
                        sql.Placeholder()
                        for _ in values
                    )

                    where_clauses.append(
                        sql.SQL(
                            "c.{field} IN ({values})"
                        ).format(
                            field=field_identifier,
                            values=placeholders,
                        )
                    )

                    params.extend(
                        values
                    )

            else:

                if payload.get("min") is not None:
                    where_clauses.append(
                        sql.SQL(
                            "c.{field} >= %s"
                        ).format(
                            field=field_identifier
                        )
                    )

                    params.append(
                        payload["min"]
                    )

                if payload.get("max") is not None:
                    where_clauses.append(
                        sql.SQL(
                            "c.{field} <= %s"
                        ).format(
                            field=field_identifier
                        )
                    )

                    params.append(
                        payload["max"]
                    )

        if objectif_campagne_ids:

            radical_column = _detect_radical_column(
                conn,
                table,
            )

            placeholders = sql.SQL(
                ", "
            ).join(
                sql.Placeholder()
                for _ in objectif_campagne_ids
            )

            if objectif_mode == "atteint":

                where_clauses.append(
                    sql.SQL(
                        """
                        EXISTS (
                            SELECT 1
                            FROM clients_campagnes AS cc
                            WHERE
                                cc."Radical_compte"
                                    = c.{radical}
                                AND cc."ID_CAMPAGNE"
                                    IN ({campaign_ids})
                                AND COALESCE(
                                    cc.conversion,
                                    0
                                ) = 1
                        )
                        """
                    ).format(
                        radical=sql.Identifier(
                            radical_column
                        ),
                        campaign_ids=placeholders,
                    )
                )

            else:

                where_clauses.append(
                    sql.SQL(
                        """
                        NOT EXISTS (
                            SELECT 1
                            FROM clients_campagnes AS cc
                            WHERE
                                cc."Radical_compte"
                                    = c.{radical}
                                AND cc."ID_CAMPAGNE"
                                    IN ({campaign_ids})
                                AND COALESCE(
                                    cc.conversion,
                                    0
                                ) = 1
                        )
                        """
                    ).format(
                        radical=sql.Identifier(
                            radical_column
                        ),
                        campaign_ids=placeholders,
                    )
                )

            params.extend(
                objectif_campagne_ids
            )

        query = sql.SQL(
            """
            SELECT c.*
            FROM {table} AS c
            """
        ).format(
            table=sql.Identifier(
                table
            )
        )

        if where_clauses:
            query += (
                sql.SQL(" WHERE ")
                + sql.SQL(" AND ").join(
                    where_clauses
                )
            )

        with conn.cursor() as cur:
            cur.execute(
                query,
                params,
            )

            rows = cur.fetchall()

            column_names = [
                description.name
                for description
                in cur.description
            ]

    return pd.DataFrame(
        rows,
        columns=column_names,
    )



# ============================================================
# POSTGRESQL-NATIVE CIBLE SELECT
# ============================================================

def build_db_cible_radicals_query(
    id_cible: str,
    *,
    exclude_rupture_relation: bool = False,
):
    """Construit un SELECT de clés exécutable dans le PostgreSQL interne.

    - cible DB interne : filtre SQL natif ;
    - cible fichier : population déjà matérialisée dans clients_cibles ;
    - datamart externe : retourne None, car sa requête ne doit jamais être
      injectée dans la base interne ni provoquer une copie implicite.
    """
    cible = get_cible(id_cible)
    if not cible:
        raise ValueError(f"Cible introuvable : {id_cible}")

    source = str(cible.get("source") or "").strip()
    source_code = str(cible.get("data_source_code") or "internal").strip() or "internal"

    if source == "Fichier plat":
        params: List[Any] = [id_cible]
        if exclude_rupture_relation:
            return (
                sql.SQL(
                    """
                    SELECT cc."Radical_compte" AS "Radical_compte"
                    FROM clients_cibles AS cc
                    JOIN clients AS c ON c.radical_compte = cc."Radical_compte"
                    WHERE cc."ID_CIBLE" = %s
                      AND LOWER(TRIM(COALESCE(c."STATUT_CLIENT"::text, ''))) <> LOWER(%s)
                    """
                ),
                [id_cible, "Rupture de relation"],
            )
        return (
            sql.SQL(
                """
                SELECT cc."Radical_compte" AS "Radical_compte"
                FROM clients_cibles AS cc
                WHERE cc."ID_CIBLE" = %s
                """
            ),
            params,
        )

    if source != "DB":
        raise ValueError(f"Source cible invalide : {source}")

    if source_code != "internal":
        return None

    try:
        filtre_str = cible.get("filtre") or "{}"
        filtre = json.loads(filtre_str) if isinstance(filtre_str, str) else (filtre_str or {})
    except Exception:
        filtre = {}

    with connection() as conn:
        table = _detect_clients_table(conn)
        clients_columns = _get_table_columns(conn, table)
        radical_column = _detect_radical_column(conn, table)
        normal_filtre, objectif_campagne_ids, objectif_mode = _split_objectif_campaign_filter(filtre or {})
        where_clauses = []
        params: List[Any] = []

        for field, payload in (normal_filtre or {}).items():
            if not isinstance(payload, dict):
                continue
            actual_field = _resolve_column_name(clients_columns, field)
            field_identifier = sql.Identifier(actual_field)

            if "values" in payload:
                raw_values = payload.get("values") or []
                values = [v for v in raw_values if v is not None and str(v).strip() != ""]
                if values:
                    placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in values)
                    where_clauses.append(sql.SQL("c.{field} IN ({values})").format(field=field_identifier, values=placeholders))
                    params.extend(values)
            else:
                if payload.get("min") is not None:
                    where_clauses.append(sql.SQL("c.{field} >= %s").format(field=field_identifier))
                    params.append(payload["min"])
                if payload.get("max") is not None:
                    where_clauses.append(sql.SQL("c.{field} <= %s").format(field=field_identifier))
                    params.append(payload["max"])

        if objectif_campagne_ids:
            placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in objectif_campagne_ids)
            operator = sql.SQL("EXISTS") if objectif_mode == "atteint" else sql.SQL("NOT EXISTS")
            where_clauses.append(
                sql.SQL(
                    """
                    {operator} (
                        SELECT 1 FROM clients_campagnes AS cc
                        WHERE cc."Radical_compte" = c.{radical}
                          AND cc."ID_CAMPAGNE" IN ({campaign_ids})
                          AND COALESCE(cc.conversion, 0) = 1
                    )
                    """
                ).format(operator=operator, radical=sql.Identifier(radical_column), campaign_ids=placeholders)
            )
            params.extend(objectif_campagne_ids)

        if exclude_rupture_relation:
            try:
                statut_column = _resolve_column_name(clients_columns, "STATUT_CLIENT")
            except Exception:
                statut_column = ""
            if statut_column:
                where_clauses.append(
                    sql.SQL("LOWER(TRIM(COALESCE(c.{field}::text, ''))) <> LOWER(%s)").format(
                        field=sql.Identifier(statut_column)
                    )
                )
                params.append("Rupture de relation")

        query = sql.SQL('SELECT c.{radical} AS "Radical_compte" FROM {table} AS c').format(
            radical=sql.Identifier(radical_column),
            table=sql.Identifier(table),
        )
        if where_clauses:
            query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where_clauses)

    return query, params

# ============================================================
# LOAD CIBLE POPULATION
# ============================================================

def load_clients_df_for_cible(
    id_cible: str,
) -> pd.DataFrame:
    """Compatibilité historique pour les petits usages.

    Ce helper ne doit plus être utilisé pour une population externe. Les cibles
    fichier sont relues depuis clients_cibles/clients et non depuis le fichier.
    """
    cible = get_cible(id_cible)
    if not cible:
        raise ValueError(f"Cible introuvable : {id_cible}")

    source_code = str(cible.get("data_source_code") or "internal").strip() or "internal"
    if source_code != "internal":
        raise RuntimeError(
            "Une population de datamart externe ne peut pas être matérialisée en DataFrame. "
            "Utilisez le DataSourceAdapter.stream_target_keys()."
        )

    built = build_db_cible_radicals_query(id_cible, exclude_rupture_relation=False)
    if built is None:
        raise RuntimeError("Cible non exécutable sur PostgreSQL interne.")
    radical_select, params = built
    with connection() as conn:
        query = sql.SQL(
            """
            SELECT c.*
            FROM clients AS c
            JOIN ({target}) AS t ON t."Radical_compte" = c.radical_compte
            """
        ).format(target=radical_select)
        with conn.cursor() as cur:
            cur.execute(query, params or [])
            rows = cur.fetchall()
            columns = [desc.name for desc in (cur.description or [])]
    return pd.DataFrame(rows, columns=columns)


def preview_clients_for_cible(
    id_cible: str,
    limit: int = 200,
) -> tuple[pd.DataFrame, int]:
    """Preview bornée pour source interne, fichier matérialisé ou datamart externe."""
    cible = get_cible(id_cible)
    if not cible:
        raise ValueError(f"Cible introuvable : {id_cible}")
    source_code = str(cible.get("data_source_code") or "internal").strip() or "internal"
    adapter = get_data_source(source_code)
    preview = adapter.preview_target(cible, limit=limit)
    return pd.DataFrame(preview.rows), int(preview.total)

