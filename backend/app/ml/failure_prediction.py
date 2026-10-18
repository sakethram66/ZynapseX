"""Separate engineering risk scoring and synthetic failure-horizon inference.

The transparent engineering score below is not a trained failure model or a
calibrated probability. The saved Random Forest adapter later in this module
predicts a synthetic scheduled-event label within a future horizon.

Engineering score:

  1. Per-metric stress s_i in [0, 1] from configurable (ok, warn, crit) limits:
        x <= ok -> 0 ;  ok..warn -> 0..0.5 ;  warn..crit -> 0.5..1 (clipped)
  2. Trend stress t in [0, 1] from the temperature / vibration slopes.
  3. Components:
        W = sum_i w_i * s_i         (weighted stress, weights sum to 1)
        M = max_i s_i               (worst single metric)
        T = max(trend stresses)
        A = anomaly score from ml/anomaly.py
  4. risk_score = 100 * clip(0.30*W + 0.55*M + 0.10*T + 0.05*A, 0, 1)
  5. Level: LOW < 25 <= MEDIUM < 50 <= HIGH < 70 <= CRITICAL (configurable)

The sum of the terms is exactly additive, so each factor's share of the score
is reported as "contribution points" (see explainability.py).
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from app.config import DEFAULT_FAILURE_SCORE_THRESHOLDS, Settings, get_settings
from app.ml.synthetic_failure_data import MODEL_FEATURES
from app.schemas import FailurePrediction

log = logging.getLogger("zynapsex.failure_prediction")

COEF_WEIGHTED = 0.30
COEF_MAX = 0.55
COEF_TREND = 0.10
COEF_ANOMALY = 0.05

TREND_TO_FACTOR = {"temp_slope": "temp_trend", "vibration_slope": "vibration_trend"}


def stress(value: float, ok: float, warn: float, crit: float) -> float:
    if value <= ok:
        return 0.0
    if value <= warn:
        return 0.5 * (value - ok) / max(warn - ok, 1e-9)
    return min(1.0, 0.5 + 0.5 * (value - warn) / max(crit - warn, 1e-9))


def trend_stress(slope_value: float, ok: float, crit: float) -> float:
    if slope_value <= ok:
        return 0.0
    return min(1.0, (slope_value - ok) / max(crit - ok, 1e-9))


def classify(score: float, thresholds: tuple[float, float, float]) -> str:
    t1, t2, t3 = thresholds
    if score < t1:
        return "LOW"
    if score < t2:
        return "MEDIUM"
    if score < t3:
        return "HIGH"
    return "CRITICAL"


def metric_stresses(features: dict[str, float], settings: Settings | None = None) -> dict[str, float]:
    s = settings or get_settings()
    return {k: stress(features[k], *lim) for k, lim in s.limits.items()}


def trend_stresses(features: dict[str, float], settings: Settings | None = None) -> dict[str, float]:
    s = settings or get_settings()
    return {k: trend_stress(features.get(k, 0.0), *lim) for k, lim in s.trend_limits.items()}


def estimate_risk(features: dict[str, float], anomaly_score: float,
                  settings: Settings | None = None) -> dict:
    """Return risk score, level, components and per-factor additive points."""
    s = settings or get_settings()
    stresses = metric_stresses(features, s)
    trends = trend_stresses(features, s)

    weighted = sum(s.weights[k] * stresses[k] for k in s.weights)
    worst_factor = max(stresses, key=stresses.get)
    worst = stresses[worst_factor]
    worst_trend_key = max(trends, key=trends.get) if trends else None
    trend_max = trends[worst_trend_key] if worst_trend_key else 0.0

    raw = (COEF_WEIGHTED * weighted + COEF_MAX * worst
           + COEF_TREND * trend_max + COEF_ANOMALY * anomaly_score)
    score = 100.0 * min(1.0, max(0.0, raw))

    # Additive attribution (points sum to 100*raw before clipping).
    points = {k: 100.0 * COEF_WEIGHTED * s.weights[k] * stresses[k] for k in s.weights}
    points[worst_factor] += 100.0 * COEF_MAX * worst
    if worst_trend_key:
        points[TREND_TO_FACTOR[worst_trend_key]] = 100.0 * COEF_TREND * trend_max
    points["anomaly"] = 100.0 * COEF_ANOMALY * anomaly_score

    return {
        "risk_score": round(score, 2),
        "risk_level": classify(score, s.risk_thresholds),
        "components": {
            "weighted_stress": round(weighted, 4),
            "worst_stress": round(worst, 4),
            "worst_factor": worst_factor,
            "trend_stress": round(trend_max, 4),
            "anomaly_score": round(anomaly_score, 4),
        },
        "stresses": {k: round(v, 4) for k, v in stresses.items()},
        "trend_stresses": {k: round(v, 4) for k, v in trends.items()},
        "points": {k: round(v, 3) for k, v in points.items()},
    }


class FailurePredictor:
    """Inference adapter for the separate synthetic-horizon classifier.

    Class scores are returned without a probability because calibration has
    not been validated. Feature importances are global drivers, not causal
    per-sample explanations.
    """

    def __init__(self, pipeline, metadata: dict):
        self.pipeline = pipeline
        self.metadata = metadata
        classifier = pipeline.named_steps["classifier"]
        self.importances = dict(zip(MODEL_FEATURES, classifier.feature_importances_))

    def predict_many(self, rows: list[dict[str, float]], sample_interval_s: float,
                     thresholds: tuple[float, float, float] = DEFAULT_FAILURE_SCORE_THRESHOLDS) -> list[FailurePrediction]:
        if not rows:
            return []
        if len(thresholds) != 3 or not 0 <= thresholds[0] < thresholds[1] < thresholds[2] <= 1:
            raise ValueError("failure score thresholds must be three increasing values in [0, 1]")
        try:
            frame = pd.DataFrame([{name: row[name] for name in MODEL_FEATURES} for row in rows],
                                 columns=MODEL_FEATURES).apply(pd.to_numeric, errors="coerce")
            if not np.isfinite(frame.to_numpy(dtype=float)).all():
                raise ValueError("model input contains missing, non-numeric, or non-finite values")
            scores = self.pipeline.predict_proba(frame)[:, list(self.pipeline.classes_).index(1)]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid failure model input: {exc}") from exc
        horizon = int(self.metadata["prediction_horizon_ticks"])
        version = str(self.metadata["model_version"])
        drivers = sorted(self.importances.items(), key=lambda item: item[1], reverse=True)[:3]
        out = []
        for row, score in zip(rows, scores):
            score = float(score)
            category = ("LOW" if score < thresholds[0] else "MEDIUM" if score < thresholds[1]
                        else "HIGH" if score < thresholds[2] else "CRITICAL")
            elevated = category in ("HIGH", "CRITICAL")
            out.append(FailurePrediction(
                available=True, model_version=version, horizon_ticks=horizon,
                horizon_seconds=round(horizon * sample_interval_s, 3),
                predicted_failure_within_horizon=elevated,
                risk_classification=category, model_score=score,
                model_score_meaning="Uncalibrated Random Forest class score from 0 to 1 (not a failure probability).",
                probability=None, probability_calibrated=False,
                top_features=[{"feature": name, "importance": float(value),
                               "observed_value": float(row[name])} for name, value in drivers],
                message=(f"Synthetic-trained classifier category is {category} for the stated horizon."
                         if elevated else f"Synthetic-trained classifier category is {category}; continue routine monitoring."),
            ))
        return out


@lru_cache(maxsize=4)
def get_failure_predictor(model_path: str | None = None) -> FailurePredictor | None:
    """Load the trained artifact once; missing/invalid artifacts disable only this model."""
    default_path = Path(__file__).resolve().parents[2] / "artifacts" / "failure_model.joblib"
    path = Path(model_path or os.getenv("FAILURE_MODEL_PATH", str(default_path)))
    if not path.is_file():
        log.warning("Failure prediction model unavailable; artifact not found: %s", path)
        return None
    try:
        artifact = joblib.load(path)
        metadata = artifact["metadata"]
        if metadata.get("scikit_learn_version") != sklearn.__version__:
            raise ValueError(
                f"artifact was trained with scikit-learn {metadata.get('scikit_learn_version')}, "
                f"but runtime has {sklearn.__version__}; retrain in this environment"
            )
        if metadata.get("features") != MODEL_FEATURES:
            raise ValueError("artifact feature list does not match this application")
        if metadata.get("probability_calibration_validated"):
            log.warning("Artifact declares calibration, but this API intentionally suppresses probability")
        return FailurePredictor(artifact["pipeline"], metadata)
    except Exception:
        log.exception("Could not load failure prediction artifact %s", path)
        return None
