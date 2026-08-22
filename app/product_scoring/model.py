from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import zlib
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import numpy as np

from app.product_scoring.constants import CARD_PRODUCTS, MODEL_VERSION
from app.storage.postgres_db import connection

logger = logging.getLogger(__name__)

NUMERIC_FIELDS = [
    "age", "nb_transaction", "vol_transaction", "nb_retrait_gab", "vol_retrait_gab",
    "nb_transaction_ecom", "vol_transaction_ecom", "nb_virement", "vol_virement",
    "solde_moyen_depots", "encours_global", "encours_conso", "encours_immo", "montant_revenu",
    "app_installed", "premiere_connex", "card_rank", "epargne_active",
    "delta_transactions", "delta_depots", "delta_revenu", "delta_encours_conso", "delta_encours_immo",
    "feedback_contacts", "feedback_conversions", "feedback_conversion_rate",
]
CATEGORICAL_FIELDS = ["statut_client", "region", "segment", "qualite"]

MODEL_SPECS: Dict[str, Dict[str, str | None]] = {
    "card_silver": {"target": "target_card_silver", "product": "card", "state_field": None, "state": None},
    "card_titanium": {"target": "target_card_titanium", "product": "card", "state_field": None, "state": None},
    "card_platinium": {"target": "target_card_platinium", "product": "card", "state_field": None, "state": None},
    "card_infinite": {"target": "target_card_infinite", "product": "card", "state_field": None, "state": None},
    "epargne": {"target": "target_epargne", "product": "epargne", "state_field": None, "state": None},
    "conso_never": {"target": "target_conso", "product": "conso", "state_field": "credit_conso_state", "state": "never"},
    "conso_finished": {"target": "target_conso", "product": "conso", "state_field": "credit_conso_state", "state": "finished"},
    "conso_active": {"target": "target_conso", "product": "conso", "state_field": "credit_conso_state", "state": "active"},
    "immo_never": {"target": "target_immo", "product": "immo", "state_field": "credit_immo_state", "state": "never"},
    "immo_finished": {"target": "target_immo", "product": "immo", "state_field": "credit_immo_state", "state": "finished"},
    "immo_active": {"target": "target_immo", "product": "immo", "state_field": "credit_immo_state", "state": "active"},
}


def model_dir() -> Path:
    return Path(os.getenv("PRODUCT_SCORING_MODEL_DIR", "/app/data/models/product_scoring")).resolve()


def _path(code: str) -> Path:
    return model_dir() / f"{MODEL_VERSION}__{code}.json"


def _meta_path(code: str) -> Path:
    return model_dir() / f"{MODEL_VERSION}__{code}.metadata.json"


def _xgb():
    try:
        import xgboost as xgb
    except Exception as exc:
        raise RuntimeError("xgboost est requis pour le scoring produits.") from exc
    return xgb


def _feedback_columns(product: str) -> tuple[str, str]:
    return f"feedback_{product}_contacts_12m", f"feedback_{product}_conversions_12m"


def _select_rows(code: str) -> list[Dict[str, Any]]:
    spec = MODEL_SPECS[code]
    target = str(spec["target"])
    product = str(spec["product"])
    contacts_col, conversions_col = _feedback_columns(product)
    where = [f"{target} IS NOT NULL"]
    params: list[Any] = []
    if spec.get("state_field") and spec.get("state"):
        where.append(f"{spec['state_field']} = %s")
        params.append(spec["state"])
    max_rows = max(20000, int(os.getenv("PRODUCT_SCORING_TRAIN_MAX_ROWS", "220000") or "220000"))
    query = f"""
        SELECT radical_compte, annee_mois, statut_client, age, region, segment, qualite,
               nb_transaction, vol_transaction, nb_retrait_gab, vol_retrait_gab,
               nb_transaction_ecom, vol_transaction_ecom, nb_virement, vol_virement,
               solde_moyen_depots, encours_global, encours_conso, encours_immo, montant_revenu,
               app_installed, premiere_connex, card_rank, epargne_active,
               delta_transactions, delta_depots, delta_revenu, delta_encours_conso, delta_encours_immo,
               {contacts_col} AS feedback_contacts,
               {conversions_col} AS feedback_conversions,
               {target} AS target
        FROM dm_product_training_monthly
        WHERE {' AND '.join(where)}
        ORDER BY CASE WHEN source='real' THEN 0 ELSE 1 END, annee_mois DESC, md5(radical_compte || ':' || annee_mois::text)
        LIMIT %s
    """
    params.append(max_rows)
    with connection(dict_rows=True) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]


def _category_map(rows: Sequence[Dict[str, Any]]) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {}
    for field in CATEGORICAL_FIELDS:
        values = sorted({str(row.get(field) or "Inconnu") for row in rows})
        if "Inconnu" not in values:
            values.append("Inconnu")
        result[field] = values
    return result


def _safe_float(value: Any) -> float:
    try:
        x = float(value or 0.0)
        if not math.isfinite(x):
            return 0.0
        return x
    except Exception:
        return 0.0


def _numeric_value(row: Dict[str, Any], field: str) -> float:
    if field == "feedback_conversion_rate":
        contacts = _safe_float(row.get("feedback_contacts"))
        conv = _safe_float(row.get("feedback_conversions"))
        return conv / contacts if contacts > 0 else 0.0
    value = _safe_float(row.get(field))
    if field in {
        "vol_transaction", "vol_retrait_gab", "vol_transaction_ecom", "vol_virement",
        "solde_moyen_depots", "encours_global", "encours_conso", "encours_immo", "montant_revenu",
    }:
        return math.log1p(max(0.0, value))
    if field.startswith("delta_"):
        return max(-2.0, min(5.0, value))
    return value


def feature_names(categories: Dict[str, List[str]]) -> List[str]:
    names = list(NUMERIC_FIELDS)
    for field in CATEGORICAL_FIELDS:
        names.extend([f"{field}::{v}" for v in categories.get(field, [])])
    return names


def build_matrix(rows: Sequence[Dict[str, Any]], categories: Dict[str, List[str]]) -> np.ndarray:
    cat_offsets: Dict[str, tuple[int, Dict[str, int]]] = {}
    offset = len(NUMERIC_FIELDS)
    for field in CATEGORICAL_FIELDS:
        vals = categories.get(field, ["Inconnu"])
        mapping = {v: idx for idx, v in enumerate(vals)}
        cat_offsets[field] = (offset, mapping)
        offset += len(vals)
    x = np.zeros((len(rows), offset), dtype=np.float32)
    for i, row in enumerate(rows):
        for j, field in enumerate(NUMERIC_FIELDS):
            x[i, j] = _numeric_value(row, field)
        for field in CATEGORICAL_FIELDS:
            start, mapping = cat_offsets[field]
            value = str(row.get(field) or "Inconnu")
            idx = mapping.get(value, mapping.get("Inconnu", 0))
            x[i, start + idx] = 1.0
    return x


def _save_atomic(booster, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="product-model-", suffix=".json", dir=path.parent, delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        booster.save_model(str(tmp_path))
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def train_model(code: str, run_date: date) -> Dict[str, Any]:
    if code not in MODEL_SPECS:
        raise ValueError(code)
    rows = _select_rows(code)
    if len(rows) < 1000:
        raise RuntimeError(f"Pas assez de données pour {code}: {len(rows)}")
    y = np.asarray([int(row.get("target") or 0) for row in rows], dtype=np.float32)
    positives = int(y.sum())
    if positives < 20:
        raise RuntimeError(f"Pas assez de positifs pour {code}: {positives}")

    categories = _category_map(rows)
    x = build_matrix(rows, categories)
    eval_mask = np.asarray([
        (zlib.crc32(f"{row.get('radical_compte')}:{row.get('annee_mois')}".encode("utf-8")) % 5) == 0
        for row in rows
    ], dtype=bool)
    if eval_mask.sum() < 100 or np.unique(y[eval_mask]).size < 2:
        eval_mask = np.zeros(len(rows), dtype=bool)
        eval_mask[::5] = True
    train_mask = ~eval_mask
    xgb = _xgb()
    names = feature_names(categories)
    train_pos = float(y[train_mask].sum())
    train_neg = float(train_mask.sum() - train_pos)
    dtrain = xgb.DMatrix(x[train_mask], label=y[train_mask], feature_names=names)
    deval = xgb.DMatrix(x[eval_mask], label=y[eval_mask], feature_names=names)
    params = {
        "objective": "binary:logistic",
        "eval_metric": ["logloss", "auc"],
        "eta": 0.08,
        "max_depth": 5,
        "min_child_weight": 4,
        "subsample": 0.85,
        "colsample_bytree": 0.9,
        "scale_pos_weight": min(20.0, train_neg / max(train_pos, 1.0)),
        "tree_method": "hist",
        "seed": 20260822,
        "nthread": max(1, int(os.getenv("PRODUCT_SCORING_XGBOOST_THREADS", "2") or "2")),
    }
    evals_result: Dict[str, Any] = {}
    logger.info("Entraînement produit démarré: model=%s rows=%s positives=%s", code, len(rows), positives)
    booster = xgb.train(
        params, dtrain, num_boost_round=140,
        evals=[(dtrain, "train"), (deval, "validation")],
        evals_result=evals_result, verbose_eval=False, early_stopping_rounds=18,
    )
    _save_atomic(booster, _path(code))
    auc_values = evals_result.get("validation", {}).get("auc") or []
    best_iteration = int(getattr(booster, "best_iteration", max(0, len(auc_values) - 1)))
    auc = float(auc_values[min(best_iteration, len(auc_values)-1)]) if auc_values else None
    metadata = {
        "model_version": MODEL_VERSION,
        "model_code": code,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "trained_month": run_date.year * 100 + run_date.month,
        "training_rows": int(train_mask.sum()),
        "validation_rows": int(eval_mask.sum()),
        "positive_rows": positives,
        "validation_auc": auc,
        "best_iteration": best_iteration,
        "categories": categories,
        "feature_names": names,
    }
    _meta_path(code).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Modèle produit entraîné: %s", metadata)
    return metadata


def load_metadata(code: str) -> Dict[str, Any]:
    p = _meta_path(code)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def model_ready(code: str, run_date: date) -> bool:
    if not _path(code).is_file() or not _meta_path(code).is_file():
        return False
    meta = load_metadata(code)
    return int(meta.get("trained_month") or 0) == (run_date.year * 100 + run_date.month)


def ensure_models(run_date: date) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for code in MODEL_SPECS:
        if model_ready(code, run_date):
            result[code] = load_metadata(code)
        else:
            result[code] = train_model(code, run_date)
    return result


def load_booster(code: str):
    xgb = _xgb()
    booster = xgb.Booster()
    booster.load_model(str(_path(code)))
    return booster


def predict(code: str, rows: Sequence[Dict[str, Any]]) -> np.ndarray:
    meta = load_metadata(code)
    categories = meta.get("categories") or {}
    x = build_matrix(rows, categories)
    xgb = _xgb()
    dmatrix = xgb.DMatrix(x, feature_names=meta.get("feature_names") or feature_names(categories))
    booster = load_booster(code)
    return np.asarray(booster.predict(dmatrix), dtype=np.float32)


def dashboard_model_metadata() -> list[Dict[str, Any]]:
    out = []
    for code in MODEL_SPECS:
        meta = load_metadata(code)
        if meta:
            out.append(meta)
    return out
