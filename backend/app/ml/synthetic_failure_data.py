"""Reproducible synthetic failure-horizon data built from the project simulator.

Labels describe a synthetic scheduled event, not an observed real transformer
failure. See backend/docs/FAILURE_MODEL.md before interpreting the target.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.simulator.generator import GridSimulator, build_fleet
from app.processing.features import FeatureWindow
from app.simulator.scenarios import Scenario

HORIZON_TICKS = 12
TARGET = "failure_within_horizon"
SENSOR_COLUMNS = [
    "temperature", "voltage", "current", "load_pct", "frequency",
    "vibration", "power_factor",
]
TREND_COLUMNS = ["temp_slope", "vibration_slope", "load_slope"]
MODEL_FEATURES = [*SENSOR_COLUMNS, *TREND_COLUMNS, "rating_kva", "rated_current_a"]
SYNTHETIC_SCENARIOS = [scenario for scenario in Scenario if scenario != Scenario.NORMAL]


def generate_dataset(episodes: int = 240, ticks: int = 100, seed: int = 73021,
                     horizon_ticks: int = HORIZON_TICKS) -> pd.DataFrame:
    """Generate independent time-series episodes; half have synthetic events.

    Event episodes end just before the scheduled event. Control episodes may
    include short, self-clearing stress injections. No event time, scenario,
    asset ID, episode ID, or future information is a model feature.
    """
    if episodes < 10 or episodes % 2:
        raise ValueError("episodes must be an even integer of at least 10")
    if ticks <= horizon_ticks + 20 or horizon_ticks < 1:
        raise ValueError("ticks must exceed horizon_ticks by at least 21")
    rng = np.random.default_rng(seed)
    fleet = build_fleet()
    rows: list[dict] = []
    n_events = episodes // 2
    for episode in range(episodes):
        has_event = episode < n_events
        asset = fleet[(episode * 7) % len(fleet)]
        episode_seed = seed + episode * 101
        sim = GridSimulator(seed=episode_seed, fleet=[asset])
        feature_window = FeatureWindow(size=10)
        onset = int(rng.integers(12, max(13, ticks // 2)))
        event_tick = int(rng.integers(max(onset + horizon_ticks + 5, ticks * 2 // 3), ticks)) if has_event else None
        scenario = SYNTHETIC_SCENARIOS[int(rng.integers(len(SYNTHETIC_SCENARIOS)))]
        control_scenario = SYNTHETIC_SCENARIOS[int(rng.integers(len(SYNTHETIC_SCENARIOS)))]
        control_duration = int(rng.integers(5, 16))
        stop_tick = event_tick - 1 if event_tick is not None else ticks
        base_time = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=episode)

        for tick in range(1, stop_tick + 1):
            if tick == onset:
                if has_event:
                    sim.inject(asset.asset_id, scenario, intensity=float(rng.uniform(0.8, 1.2)))
                elif episode % 3 != 0:
                    sim.inject(asset.asset_id, control_scenario,
                               intensity=float(rng.uniform(0.5, 1.0)),
                               duration_ticks=control_duration)
            reading = sim.tick(base_time + timedelta(seconds=tick * 2))[0]
            feature_window.push(reading)
            trends = feature_window.trends(asset.asset_id)
            target = int(event_tick is not None and 1 <= event_tick - tick <= horizon_ticks)
            rows.append({
                "episode_id": f"E{episode:04d}", "asset_id": asset.asset_id,
                "episode_tick": tick, "scenario": scenario.value if has_event else (
                    control_scenario.value if episode % 3 else "normal"),
                "episode_had_failure": int(has_event), "failure_tick": event_tick,
                "failure_within_horizon": target,
                "timestamp": reading.timestamp.isoformat(),
                "temperature": reading.temperature, "voltage": reading.voltage,
                "current": reading.current, "load_pct": reading.load_pct,
                "frequency": reading.frequency, "vibration": reading.vibration,
                "power_factor": reading.power_factor, "rating_kva": asset.rating_kva,
                "rated_current_a": asset.rated_current_a,
                **trends,
                "label_source": "synthetic_scenario_schedule",
            })
    frame = pd.DataFrame(rows)
    if frame.empty or frame[TARGET].nunique() != 2:
        raise ValueError("generated data must contain both target classes")
    return frame


def split_by_transformer(frame: pd.DataFrame, test_size: float = 0.2,
                         seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep each transformer ID and all its episodes wholly in one split."""
    from sklearn.model_selection import GroupShuffleSplit

    groups = frame[["episode_id", "asset_id", "episode_had_failure"]].drop_duplicates()
    if groups["episode_id"].duplicated().any():
        raise ValueError("episode_had_failure must be consistent within each episode")
    if groups.asset_id.nunique() < 2:
        raise ValueError("need at least two transformer IDs for a group split")
    split = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_ix, test_ix = next(split.split(frame, groups=frame.asset_id))
    train = frame.iloc[train_ix].copy()
    test = frame.iloc[test_ix].copy()
    if set(train.episode_id) & set(test.episode_id):
        raise AssertionError("episode leakage in generated split")
    if set(train.asset_id) & set(test.asset_id):
        raise AssertionError("transformer leakage in generated split")
    if train[TARGET].nunique() < 2 or test[TARGET].nunique() < 2:
        raise ValueError("train and test partitions must each contain both target classes")
    return train, test
