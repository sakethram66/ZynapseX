"""Transparent failure-RISK estimation (a prototype risk index, not a trained model).

There is no labelled failure dataset, so nothing here is trained on failures and
the output is NOT a calibrated probability of failure. It is a documented,
deterministic engineering score:

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

from app.config import Settings, get_settings

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
