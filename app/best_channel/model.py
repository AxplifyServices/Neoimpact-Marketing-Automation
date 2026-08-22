from __future__ import annotations

import json
import logging
import os
import tempfile
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

from app.best_channel.history import CANONICAL_CHANNELS, age_band, training_weight

logger = logging.getLogger(__name__)
MODEL_CODE = "best_channel_xgboost_v2"
AGE_BANDS = ["0-17", "18-24", "25-34", "35-49", "50-59", "60+", "Inconnu"]


def model_dir() -> Path:
    return Path(os.getenv("BEST_CHANNEL_MODEL_DIR", "/app/data/models/best_channel")).resolve()


def model_path() -> Path:
    return model_dir() / f"{MODEL_CODE}.json"


def metadata_path() -> Path:
    return model_dir() / f"{MODEL_CODE}.metadata.json"


def model_exists() -> bool:
    return model_path().is_file() and metadata_path().is_file()


def _xgboost():
    try:
        import xgboost as xgb
    except Exception as exc:
        raise RuntimeError("xgboost est requis pour le modèle Best Channel.") from exc
    return xgb


def load_metadata() -> Dict[str, Any]:
    if not metadata_path().is_file():
        return {}
    try:
        data = json.loads(metadata_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_model():
    xgb = _xgboost()
    booster = xgb.Booster()
    booster.load_model(str(model_path()))
    return booster


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def _categories_from_rows(rows: Sequence[Sequence[Any]]) -> Dict[str, List[str]]:
    regions = sorted({str(_row_value(row, "region", 2) or "Inconnue") for row in rows})
    return {"age_bands": AGE_BANDS, "regions": regions, "channels": CANONICAL_CHANNELS}

def _feature_names(categories: Dict[str, List[str]]) -> List[str]:
    names = [f"age::{x}" for x in categories["age_bands"]]
    names += [f"region::{x}" for x in categories["regions"]]
    names += [f"channel::{x}" for x in categories["channels"]]
    return names


def build_matrix(items: Sequence[Tuple[str, str, str]], categories: Dict[str, List[str]]) -> np.ndarray:
    ages = {v: i for i, v in enumerate(categories["age_bands"])}
    regions = {v: i for i, v in enumerate(categories["regions"])}
    channels = {v: i for i, v in enumerate(categories["channels"])}
    a_len, r_len, c_len = len(ages), len(regions), len(channels)
    x = np.zeros((len(items), a_len + r_len + c_len), dtype=np.float32)
    for i, (a, r, c) in enumerate(items):
        x[i, ages.get(a, ages.get("Inconnu", 0))] = 1.0
        if r in regions:
            x[i, a_len + regions[r]] = 1.0
        if c in channels:
            x[i, a_len + r_len + channels[c]] = 1.0
    return x


def train_model(conn) -> Dict[str, Any]:
    xgb = _xgboost()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT radical_compte, tranche_age, COALESCE(region,'Inconnue') AS region, canal,
                   resultat_bloc, objectif_valide
            FROM dm_best_channel_interactions
            WHERE finalized_at IS NOT NULL
              AND observed_at >= CURRENT_DATE - INTERVAL '12 months'
              AND canal = ANY(%s)
            ORDER BY observed_at, radical_compte
            """,
            (CANONICAL_CHANNELS,),
        )
        rows = cur.fetchall()
    if len(rows) < 500:
        raise RuntimeError(f"Pas assez de lignes Best Channel pour entraîner le modèle: {len(rows)}")

    normalized = [
        (
            str(_row_value(r, "tranche_age", 1) or "Inconnu"),
            str(_row_value(r, "region", 2) or "Inconnue"),
            str(_row_value(r, "canal", 3) or ""),
        )
        for r in rows
    ]
    categories = _categories_from_rows(rows)
    x = build_matrix(normalized, categories)
    y = np.asarray([int(_row_value(r, "objectif_valide", 5) or 0) for r in rows], dtype=np.float32)
    weights = np.asarray([
        training_weight(
            _row_value(r, "resultat_bloc", 4),
            int(_row_value(r, "objectif_valide", 5) or 0),
        )
        for r in rows
    ], dtype=np.float32)
    radicals = [str(_row_value(r, "radical_compte", 0) or "") for r in rows]

    if int(y.sum()) < 20:
        raise RuntimeError(f"Pas assez de conversions pour entraîner Best Channel: {int(y.sum())}")
    eval_mask = np.asarray([(zlib.crc32(v.encode("utf-8")) % 5) == 0 for v in radicals], dtype=bool)
    if eval_mask.sum() < 50 or np.unique(y[eval_mask]).size < 2:
        eval_mask = np.zeros(len(rows), dtype=bool)
        eval_mask[::5] = True
    train_mask = ~eval_mask

    feature_names = _feature_names(categories)
    dtrain = xgb.DMatrix(x[train_mask], label=y[train_mask], weight=weights[train_mask], feature_names=feature_names)
    deval = xgb.DMatrix(x[eval_mask], label=y[eval_mask], weight=weights[eval_mask], feature_names=feature_names)
    train_pos = float(y[train_mask].sum())
    train_neg = float(train_mask.sum() - train_pos)
    params = {
        "objective": "binary:logistic",
        "eval_metric": ["logloss", "auc"],
        "eta": 0.08,
        "max_depth": 5,
        "min_child_weight": 4,
        "subsample": 0.85,
        "colsample_bytree": 0.9,
        "scale_pos_weight": train_neg / max(train_pos, 1.0),
        "tree_method": "hist",
        "seed": 20260822,
        "nthread": max(1, int(os.getenv("BEST_CHANNEL_XGBOOST_THREADS", "2") or "2")),
    }
    evals_result: Dict[str, Any] = {}
    logger.info(
        "Entraînement Best Channel démarré: rows=%s positives=%s regions=%s channels=%s",
        len(rows),
        int(y.sum()),
        len(categories.get("regions") or []),
        len(categories.get("channels") or []),
    )
    booster = xgb.train(
        params,
        dtrain,
        num_boost_round=180,
        evals=[(dtrain, "train"), (deval, "validation")],
        evals_result=evals_result,
        verbose_eval=False,
        early_stopping_rounds=20,
    )

    model_dir().mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="best-channel-", suffix=".json", dir=model_dir(), delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        booster.save_model(str(tmp_path))
        os.replace(tmp_path, model_path())
    finally:
        tmp_path.unlink(missing_ok=True)

    auc_values = evals_result.get("validation", {}).get("auc") or []
    best_iteration = int(getattr(booster, "best_iteration", max(0, len(auc_values) - 1)))
    auc = float(auc_values[min(best_iteration, len(auc_values) - 1)]) if auc_values else None
    metadata = {
        "model_code": MODEL_CODE,
        "algorithm": "XGBoost",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_rows": int(train_mask.sum()),
        "validation_rows": int(eval_mask.sum()),
        "positive_rows": int(y.sum()),
        "validation_auc": auc,
        "best_iteration": best_iteration,
        "categories": categories,
        "feature_names": feature_names,
        "model_path": str(model_path()),
    }
    metadata_path().write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Modèle Best Channel entraîné et sauvegardé: %s", metadata)
    return metadata


def _model_is_stale(metadata: Dict[str, Any], *, max_age_days: int = 183) -> bool:
    raw = str(metadata.get("trained_at") or "").strip()
    if not raw:
        return True
    try:
        trained_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if trained_at.tzinfo is None:
            trained_at = trained_at.replace(tzinfo=timezone.utc)
    except Exception:
        return True
    age = datetime.now(timezone.utc) - trained_at.astimezone(timezone.utc)
    return age.days >= max_age_days


def get_or_train_model(conn):
    if model_exists():
        metadata = load_metadata()
        if metadata and not _model_is_stale(metadata):
            return load_model(), metadata, False
        logger.info("Modèle Best Channel absent ou âgé de plus de 6 mois: réentraînement.")
    metadata = train_model(conn)
    return load_model(), metadata, True


def score_client_batch(
    booster,
    metadata: Dict[str, Any],
    profiles: Sequence[Tuple[str, str]],
) -> List[List[Tuple[str, float]]]:
    """Score tous les canaux pour un lot de clients en une seule DMatrix."""
    if not profiles:
        return []
    xgb = _xgboost()
    categories = metadata.get("categories") or {}
    if not categories:
        raise RuntimeError("Métadonnées du modèle Best Channel incomplètes.")
    items = [
        (tranche_age, region, channel)
        for tranche_age, region in profiles
        for channel in CANONICAL_CHANNELS
    ]
    x = build_matrix(items, categories)
    dmatrix = xgb.DMatrix(
        x,
        feature_names=metadata.get("feature_names") or _feature_names(categories),
    )
    raw_scores = booster.predict(dmatrix).reshape(len(profiles), len(CANONICAL_CHANNELS))
    rankings: List[List[Tuple[str, float]]] = []
    for client_scores in raw_scores:
        ranking = sorted(
            zip(CANONICAL_CHANNELS, [float(value) for value in client_scores]),
            key=lambda item: item[1],
            reverse=True,
        )
        rankings.append(ranking)
    return rankings
