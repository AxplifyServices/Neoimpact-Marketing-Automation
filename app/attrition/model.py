from __future__ import annotations

import json
import logging
import os
import tempfile
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Sequence

import numpy as np

logger = logging.getLogger(__name__)

MODEL_CODE = "attrition_xgboost_v1"
FEATURES = [
    "avoirs",
    "flux_crediteurs",
    "flux_debiteurs",
    "var_avoirs_1m",
    "var_avoirs_3m",
    "var_avoirs_6m",
    "var_avoirs_12m",
    "var_flux_crediteurs_1m",
    "var_flux_crediteurs_3m",
    "var_flux_crediteurs_6m",
    "var_flux_crediteurs_12m",
    "var_flux_debiteurs_1m",
    "var_flux_debiteurs_3m",
    "var_flux_debiteurs_6m",
    "var_flux_debiteurs_12m",
]


def model_dir() -> Path:
    return Path(os.getenv("ATTRITION_MODEL_DIR", "/app/data/models/attrition")).resolve()


def model_path() -> Path:
    return model_dir() / f"{MODEL_CODE}.json"


def metadata_path() -> Path:
    return model_dir() / f"{MODEL_CODE}.metadata.json"


def model_exists() -> bool:
    return model_path().is_file()


def load_metadata() -> Dict[str, Any]:
    path = metadata_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.exception("Impossible de lire les métadonnées du modèle attrition")
        return {}


def _xgboost():
    try:
        import xgboost as xgb
    except Exception as exc:  # pragma: no cover - message opérationnel
        raise RuntimeError(
            "xgboost est requis pour le scoring attrition. Vérifier requirements.txt et reconstruire l'image backend."
        ) from exc
    return xgb


def load_model():
    path = model_path()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    xgb = _xgboost()
    booster = xgb.Booster()
    booster.load_model(str(path))
    return booster


def _to_float(value: Any) -> float:
    if value is None:
        return np.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def matrix_from_rows(rows: Sequence[Sequence[Any]], *, feature_offset: int = 1) -> np.ndarray:
    out = np.empty((len(rows), len(FEATURES)), dtype=np.float32)
    for i, row in enumerate(rows):
        for j in range(len(FEATURES)):
            out[i, j] = _to_float(row[feature_offset + j])
    return out


def train_model(conn) -> Dict[str, Any]:
    """Entraîne un XGBoost à partir du datamart historique.

    Tous les cas positifs sont conservés. Pour garder un MVP léger, environ
    5 % des lignes négatives sont prises via un hash déterministe. Cela évite
    de charger plusieurs millions de lignes en RAM tout en gardant toutes les
    ruptures disponibles.
    """
    xgb = _xgboost()

    columns_sql = ", ".join(FEATURES)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM dm_attrition_variables WHERE attrition = 1")
        positives_total = int((cur.fetchone() or [0])[0] or 0)
        if positives_total < 10:
            raise RuntimeError(
                f"Pas assez de ruptures pour entraîner le modèle attrition: {positives_total}."
            )

        cur.execute(
            f"""
            SELECT radical_compte, {columns_sql}, attrition
            FROM dm_attrition_variables
            WHERE attrition = 1
               OR (
                    attrition = 0
                    AND MOD((hashtextextended(radical_compte || ':' || annee_mois::TEXT, 0) & 2147483647), 20) = 0
               )
            ORDER BY annee_mois, radical_compte
            """
        )
        rows = cur.fetchall()

    if not rows:
        raise RuntimeError("Le datamart attrition ne contient aucune ligne d'entraînement.")

    x = matrix_from_rows(rows, feature_offset=1)
    y = np.asarray([int(row[1 + len(FEATURES)] or 0) for row in rows], dtype=np.float32)
    radicals = [str(row[0]) for row in rows]

    eval_mask = np.asarray(
        [(zlib.crc32(radical.encode("utf-8")) % 5) == 0 for radical in radicals],
        dtype=bool,
    )
    if eval_mask.sum() < 20 or np.unique(y[eval_mask]).size < 2:
        eval_mask = np.zeros(len(rows), dtype=bool)
        eval_mask[::5] = True

    train_mask = ~eval_mask
    if np.unique(y[train_mask]).size < 2:
        raise RuntimeError("Le dataset d'entraînement ne contient pas les deux classes 0/1.")

    train_pos = int(y[train_mask].sum())
    train_neg = int(train_mask.sum() - train_pos)
    scale_pos_weight = float(train_neg / max(train_pos, 1))

    dtrain = xgb.DMatrix(x[train_mask], label=y[train_mask], feature_names=FEATURES)
    deval = xgb.DMatrix(x[eval_mask], label=y[eval_mask], feature_names=FEATURES)
    evals_result: Dict[str, Any] = {}

    params = {
        "objective": "binary:logistic",
        "eval_metric": ["logloss", "auc"],
        "eta": 0.08,
        "max_depth": 5,
        "min_child_weight": 5,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "lambda": 1.0,
        "alpha": 0.1,
        "scale_pos_weight": scale_pos_weight,
        "tree_method": "hist",
        "seed": 20260821,
        "nthread": max(1, int(os.getenv("ATTRITION_XGBOOST_THREADS", "2") or "2")),
    }

    booster = xgb.train(
        params,
        dtrain,
        num_boost_round=250,
        evals=[(dtrain, "train"), (deval, "validation")],
        evals_result=evals_result,
        verbose_eval=False,
        early_stopping_rounds=25,
    )

    preds = booster.predict(deval)
    threshold = float(os.getenv("ATTRITION_RISK_THRESHOLD", "0.5") or "0.5")
    predicted = (preds >= threshold).astype(np.int8)
    actual = y[eval_mask].astype(np.int8)
    tp = int(((predicted == 1) & (actual == 1)).sum())
    fp = int(((predicted == 1) & (actual == 0)).sum())
    fn = int(((predicted == 0) & (actual == 1)).sum())
    tn = int(((predicted == 0) & (actual == 0)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    model_dir().mkdir(parents=True, exist_ok=True)
    target_model = model_path()
    with tempfile.NamedTemporaryFile(prefix="attrition-", suffix=".json", dir=model_dir(), delete=False) as tmp:
        tmp_model = Path(tmp.name)
    try:
        booster.save_model(str(tmp_model))
        os.replace(tmp_model, target_model)
    finally:
        if tmp_model.exists():
            tmp_model.unlink(missing_ok=True)

    validation_auc = None
    try:
        values = evals_result.get("validation", {}).get("auc") or []
        if values:
            best_iteration = int(getattr(booster, "best_iteration", len(values) - 1))
            best_iteration = min(max(best_iteration, 0), len(values) - 1)
            validation_auc = float(values[best_iteration])
    except Exception:
        validation_auc = None

    metadata = {
        "model_code": MODEL_CODE,
        "algorithm": "XGBoost",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "features": FEATURES,
        "training_rows": int(train_mask.sum()),
        "validation_rows": int(eval_mask.sum()),
        "positive_rows_total": positives_total,
        "positive_rows_training": train_pos,
        "negative_rows_training": train_neg,
        "validation_auc": validation_auc,
        "validation_precision": precision,
        "validation_recall": recall,
        "validation_confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "risk_threshold": threshold,
        "best_iteration": int(getattr(booster, "best_iteration", 0)),
        "model_path": str(target_model),
    }
    metadata_path().write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Modèle attrition entraîné et sauvegardé: %s", metadata)
    return metadata


def get_or_train_model(conn):
    if model_exists():
        return load_model(), load_metadata(), False
    metadata = train_model(conn)
    return load_model(), metadata, True
