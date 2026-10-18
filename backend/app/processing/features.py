"""Feature engineering: turns raw readings into derived, comparable features.

Derived features (per reading):
  current_ratio     current / rated current
  voltage_dev_pct   |V - 11 kV| / 11 kV * 100
  frequency_dev_hz  |f - 50 Hz|
  pf_shortfall      max(0, 0.95 - power factor)
Trend features (per rolling window, needs >= 3 samples):
  temp_slope, vibration_slope, load_slope   least-squares slope per sample
"""
from __future__ import annotations

from collections import deque

import numpy as np

from app.schemas import AssetInfo, SensorReading
from app.simulator.generator import NOMINAL_FREQUENCY_HZ, NOMINAL_VOLTAGE_KV

PF_TARGET = 0.95
MIN_TREND_SAMPLES = 3
TREND_SAMPLES = 10  # slope is fitted over at most the last N samples

# Order used for the anomaly model's feature vector.
MODEL_FEATURES = [
    "voltage_dev_pct", "current_ratio", "temperature", "frequency_dev_hz",
    "load_pct", "vibration", "pf_shortfall",
]


def derive(reading: SensorReading, asset: AssetInfo) -> dict[str, float]:
    return {
        "temperature": reading.temperature,
        "load_pct": reading.load_pct,
        "vibration": reading.vibration,
        "current_ratio": reading.current / asset.rated_current_a if asset.rated_current_a else 0.0,
        "voltage_dev_pct": abs(reading.voltage - NOMINAL_VOLTAGE_KV) / NOMINAL_VOLTAGE_KV * 100.0,
        "frequency_dev_hz": abs(reading.frequency - NOMINAL_FREQUENCY_HZ),
        "pf_shortfall": max(0.0, PF_TARGET - reading.power_factor),
    }


def slope(values: list[float]) -> float:
    """Least-squares slope per sample; 0.0 if too few points."""
    n = len(values)
    if n < MIN_TREND_SAMPLES:
        return 0.0
    x = np.arange(n, dtype=float)
    y = np.asarray(values, dtype=float)
    xm = x.mean()
    denom = float(((x - xm) ** 2).sum())
    return float(((x - xm) * (y - y.mean())).sum() / denom) if denom else 0.0


class FeatureWindow:
    """Rolling per-asset window of recent readings."""

    def __init__(self, size: int = 30):
        self.size = size
        self._buf: dict[str, deque[SensorReading]] = {}

    def push(self, reading: SensorReading) -> None:
        self._buf.setdefault(reading.asset_id, deque(maxlen=self.size)).append(reading)

    def history(self, asset_id: str) -> list[SensorReading]:
        return list(self._buf.get(asset_id, []))

    def trends(self, asset_id: str) -> dict[str, float]:
        h = self.history(asset_id)[-TREND_SAMPLES:]
        return {
            "temp_slope": slope([r.temperature for r in h]),
            "vibration_slope": slope([r.vibration for r in h]),
            "load_slope": slope([r.load_pct for r in h]),
        }

    def features(self, reading: SensorReading, asset: AssetInfo) -> dict[str, float]:
        """Derived features for `reading` plus trend features from the window.
        Call after `push(reading)`."""
        out = derive(reading, asset)
        out.update(self.trends(reading.asset_id))
        return out
