from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from psycopg import sql

OBJECTIVE_FILTER_KEY = "__objectif_campagnes__"


def split_objective_filter(filtre: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str], str]:
    normal = dict(filtre or {})
    raw = normal.pop(OBJECTIVE_FILTER_KEY, None)
    ids: List[str] = []
    mode = "atteint"
    if isinstance(raw, dict):
        mode = str(raw.get("mode") or "atteint").strip().lower()
        values = raw.get("values") or []
        if isinstance(values, (list, tuple, set)):
            ids = [str(value).strip() for value in values if str(value or "").strip()]
    if mode not in {"atteint", "non_atteint"}:
        mode = "atteint"
    return normal, ids, mode


def resolve_column(columns: Sequence[str], requested: str, field_mapping: Mapping[str, str] | None = None) -> str:
    mapped = (field_mapping or {}).get(str(requested), str(requested))
    lookup = {str(column).lower(): str(column) for column in columns}
    resolved = lookup.get(str(mapped).lower())
    if not resolved:
        raise ValueError(f"Colonne source inconnue : {requested}")
    return resolved


def build_standard_where(
    filtre: Dict[str, Any],
    *,
    columns: Sequence[str],
    field_mapping: Mapping[str, str] | None = None,
) -> Tuple[List[Any], List[Any], List[str], str]:
    normal, objective_ids, objective_mode = split_objective_filter(filtre or {})
    where: List[Any] = []
    params: List[Any] = []

    for field, payload in normal.items():
        if not isinstance(payload, dict):
            continue
        actual = resolve_column(columns, field, field_mapping)
        field_id = sql.Identifier(actual)
        if "values" in payload:
            values = [
                value
                for value in (payload.get("values") or [])
                if value is not None and str(value).strip() != ""
            ]
            if values:
                placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in values)
                where.append(sql.SQL("c.{field} IN ({values})").format(field=field_id, values=placeholders))
                params.extend(values)
        else:
            if payload.get("min") is not None:
                where.append(sql.SQL("c.{field} >= %s").format(field=field_id))
                params.append(payload["min"])
            if payload.get("max") is not None:
                where.append(sql.SQL("c.{field} <= %s").format(field=field_id))
                params.append(payload["max"])

    return where, params, objective_ids, objective_mode
