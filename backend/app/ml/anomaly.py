"""Anomaly detection (unsupervised, no failure labels involved).

Two detectors are combined, both fitted ONLY on simulated *normal-operation*
data (no scenarios injected):

1. Isolation Forest (scikit-learn, fixed random_state)
   raw = -score_samples(x); calibrated on a HELD-OUT normal sample (different
   simulator seed) so its median maps to 0 and its 99.5th percentile maps to
   0.5, clipped to [0, 1].
2. Robust-ish z-score baseline: max over features of |x - mean| / max(std, floor),
   mapped as clip((max_z - 3) / 6, 0, 1)  (max_z = 6 -> 0.5, max_z = 9 -> 1.0).

anomaly_score = max(isolation_forest_score, zscore_score);  is_anomaly = score >= 0.5.

This is a statistical novelty detector for the SIMULATED environment. It has no
reported accuracy because there is no labelled ground truth to measure against.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.processing.features import MODEL_FEATURES, derive
from app.simulator.generator import GridSimulator

# Minimum std used in z-scores, so near-constant features don't explode.
STD_FLOORS = {
    "voltage_dev_pct": 0.2,
    "current_ratio": 0.03,
    "temperature": 2.0,
    "frequency_dev_hz": 0.02,
    "load_pct": 3.0,
    "vibration": 0.15,
    "pf_shortfall": 0.01,
}
ANOMALY_THRESHOLD = 0.5
TRAIN_TICKS = 100
TRAIN_SEEDS = (1042, 1043, 1044)  # distinct from the runtime simulator seed
CALIBRATION_SEED = 2042           # held-out normal data for score calibration
CALIBRATION_PERCENTILE = 99.5


def nominal_training_frame(ticks: int = TRAIN_TICKS, seeds: tuple[int, ...] = TRAIN_SEEDS) -> pd.DataFrame:
    """Generate normal-operation feature rows from the simulator (no scenarios).
    Several seeds are pooled so the model sees varied per-asset operating points."""
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for seed in seeds:
        sim = GridSimulator(seed=seed)
        assets = {a.asset_id: a for a in sim.fleet}
        for _ in range(ticks):
            for r in sim.tick(ts):
                f = derive(r, assets[r.asset_id])
                rows.append([f[k] for k in MODEL_FEATURES])
    return pd.DataFrame(rows, columns=MODEL_FEATURES)


class AnomalyDetector:
    def __init__(self, n_estimators: int = 100, random_state: int = 0):
        self.n_estimators = n_estimators
        self.random_state = random_state
        self._fitted = False

    def fit(self, frame: pd.DataFrame, calibration: pd.DataFrame | None = None) -> "AnomalyDetector":
        self.mean_ = frame[MODEL_FEATURES].mean()
        std = frame[MODEL_FEATURES].std(ddof=0)
        self.std_ = pd.Series({k: max(float(std[k]), STD_FLOORS[k]) for k in MODEL_FEATURES})
        self.forest_ = IsolationForest(
            n_estimators=self.n_estimators, random_state=self.random_state, contamination="auto"
        ).fit(frame[MODEL_FEATURES].values)
        calib = calibration if calibration is not None else frame
        raw = -self.forest_.score_samples(calib[MODEL_FEATURES].values)
        self.raw_p50_ = float(np.percentile(raw, 50))
        self.raw_p99_ = float(np.percentile(raw, CALIBRATION_PERCENTILE))
        self._fitted = True
        return self

    def score(self, features: dict[str, float]) -> dict:
        return self.score_many([features])[0]

    def score_many(self, rows: list[dict[str, float]]) -> list[dict]:
        """Score several feature dicts with ONE forest call (much cheaper than one by one)."""
        if not self._fitted:
            raise RuntimeError("AnomalyDetector is not fitted")
        if not rows:
            return []
        x = np.array([[r[k] for k in MODEL_FEATURES] for r in rows], dtype=float)
        raw = -self.forest_.score_samples(x)
        span = max(self.raw_p99_ - self.raw_p50_, 1e-9)
        iso = np.clip(0.5 * (raw - self.raw_p50_) / span, 0.0, 1.0)
        mean = self.mean_[MODEL_FEATURES].values.astype(float)
        std = self.std_[MODEL_FEATURES].values.astype(float)
        z_all = np.abs(x - mean) / std

        out = []
        for i in range(len(rows)):
            z = dict(zip(MODEL_FEATURES, z_all[i]))
            max_z = float(z_all[i].max())
            z_score = float(np.clip((max_z - 3.0) / 6.0, 0.0, 1.0))
            score = max(float(iso[i]), z_score)
            top = sorted(z.items(), key=lambda kv: kv[1], reverse=True)[:3]
            out.append({
                "anomaly_score": round(score, 4),
                "is_anomaly": score >= ANOMALY_THRESHOLD,
                "isolation_forest_score": round(float(iso[i]), 4),
                "zscore_score": round(z_score, 4),
                "max_abs_z": round(max_z, 3),
                "top_deviations": [{"feature": k, "abs_z": round(float(v), 2)} for k, v in top],
            })
        return out


@lru_cache
def get_detector() -> AnomalyDetector:
    """Fit once per process (deterministic: fixed seeds)."""
    calibration = nominal_training_frame(seeds=(CALIBRATION_SEED,))
    return AnomalyDetector().fit(nominal_training_frame(), calibration)
