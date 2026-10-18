"""Central configuration. Everything is overridable through environment variables
(see .env.example). No secrets live here."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


# --------------------------------------------------------------------------- #
# Engineering limits.  Each metric has three points: (ok, warn, crit).
#   value <= ok   -> stress 0.0
#   ok..warn      -> stress 0.0 .. 0.5
#   warn..crit    -> stress 0.5 .. 1.0   (clipped at 1.0)
# These are ASSUMED limits for a simulated distribution-transformer fleet.
# They are not manufacturer data. Override per deployment as needed.
# "Derived" metrics are computed in processing/features.py.
# --------------------------------------------------------------------------- #
DEFAULT_LIMITS: dict[str, tuple[float, float, float]] = {
    "temperature": (65.0, 80.0, 95.0),         # deg C
    "load_pct": (75.0, 90.0, 105.0),           # % of rating
    "current_ratio": (0.80, 0.95, 1.15),       # current / rated current
    "vibration": (2.5, 4.5, 7.0),              # mm/s RMS
    "voltage_dev_pct": (2.0, 5.0, 10.0),       # |V - Vnom| / Vnom * 100
    "frequency_dev_hz": (0.10, 0.30, 0.60),    # |f - 50|
    "pf_shortfall": (0.03, 0.10, 0.20),        # max(0, 0.95 - power factor)
}

# Trend limits: slope per sample (ok, crit). Stress is linear between them.
DEFAULT_TREND_LIMITS: dict[str, tuple[float, float]] = {
    "temp_slope": (0.15, 1.00),        # deg C per sample
    "vibration_slope": (0.03, 0.25),   # mm/s per sample
}

# Weights for the weighted-sum component of the risk score (sum to 1.0).
DEFAULT_WEIGHTS: dict[str, float] = {
    "temperature": 0.25,
    "load_pct": 0.18,
    "current_ratio": 0.15,
    "vibration": 0.20,
    "voltage_dev_pct": 0.07,
    "frequency_dev_hz": 0.05,
    "pf_shortfall": 0.10,
}

# Risk level cut-offs on the 0-100 risk score: [0,t1) LOW, [t1,t2) MEDIUM,
# [t2,t3) HIGH, [t3,100] CRITICAL.
DEFAULT_RISK_THRESHOLDS: tuple[float, float, float] = (25.0, 50.0, 70.0)

# Uncalibrated Random Forest class-score bands. These are UI/alerting defaults,
# not failure probabilities or validated safety thresholds.
DEFAULT_FAILURE_SCORE_THRESHOLDS: tuple[float, float, float] = (0.20, 0.40, 0.65)


@dataclass(frozen=True)
class Settings:
    app_name: str = "ZynapseX Smart Grid Intelligence API"
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./zynapsex.db"))
    cors_origins: list[str] = field(
        default_factory=lambda: _env_list(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        )
    )
    # simulator / pipeline
    sample_interval_s: float = field(default_factory=lambda: _env_float("SAMPLE_INTERVAL_S", 2.0))
    simulator_seed: int = field(default_factory=lambda: _env_int("SIMULATOR_SEED", 42))
    autostart_simulator: bool = field(default_factory=lambda: _env_bool("AUTOSTART_SIMULATOR", True))
    window_size: int = field(default_factory=lambda: _env_int("FEATURE_WINDOW", 30))
    scenario_ramp_ticks: int = field(default_factory=lambda: _env_int("SCENARIO_RAMP_TICKS", 15))
    # persistence
    readings_keep_per_asset: int = field(default_factory=lambda: _env_int("READINGS_KEEP_PER_ASSET", 3000))
    predictions_keep_per_asset: int = field(default_factory=lambda: _env_int("PREDICTIONS_KEEP_PER_ASSET", 1000))
    prune_every_n_ticks: int = field(default_factory=lambda: _env_int("PRUNE_EVERY_N_TICKS", 50))
    # decision support / what-if
    alert_stress_warn: float = field(default_factory=lambda: _env_float("ALERT_STRESS_WARN", 0.5))
    alert_stress_crit: float = field(default_factory=lambda: _env_float("ALERT_STRESS_CRIT", 1.0))
    recommendation_cooldown_ticks: int = field(default_factory=lambda: _env_int("RECOMMENDATION_COOLDOWN_TICKS", 30))
    sim_load_limit_pct: float = field(default_factory=lambda: _env_float("SIM_LOAD_LIMIT_PCT", 100.0))
    sim_caution_pct: float = field(default_factory=lambda: _env_float("SIM_CAUTION_PCT", 90.0))
    # model parameters
    limits: dict = field(default_factory=lambda: dict(DEFAULT_LIMITS))
    trend_limits: dict = field(default_factory=lambda: dict(DEFAULT_TREND_LIMITS))
    weights: dict = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    risk_thresholds: tuple = DEFAULT_RISK_THRESHOLDS
    failure_score_thresholds: tuple = field(default_factory=lambda: tuple(
        float(x.strip()) for x in os.getenv("FAILURE_SCORE_THRESHOLDS", "0.20,0.40,0.65").split(",")
    ))
    # deployment label only; does not change behaviour
    deployment_target: str = field(default_factory=lambda: os.getenv("DEPLOYMENT_TARGET", "local"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
