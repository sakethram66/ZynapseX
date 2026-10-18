"""Shared test helpers (no third-party test dependencies)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.ml.explainability import build_assessment
from app.processing.features import FeatureWindow
from app.simulator.generator import GridSimulator
from app.simulator.scenarios import Scenario

TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def run_scenario(scenario=Scenario.NORMAL, intensity=1.0, ticks=40, warm=30, seed=42, asset="T17"):
    """Warm up on normal data, inject `scenario` on `asset`, and return a list of
    (reading, features, assessment) for that asset, one per tick after injection."""
    sim = GridSimulator(seed=seed)
    fw = FeatureWindow()
    assets = {a.asset_id: a for a in sim.fleet}
    for _ in range(warm):
        for r in sim.tick(TS):
            fw.push(r)
    if scenario != Scenario.NORMAL:
        sim.inject(asset, scenario, intensity)
    out = []
    for _ in range(ticks):
        for r in sim.tick(TS):
            fw.push(r)
            if r.asset_id == asset:
                f = fw.features(r, assets[asset])
                out.append((r, f, build_assessment(r, f)))
    return out
