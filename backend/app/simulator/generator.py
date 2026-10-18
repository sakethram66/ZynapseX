"""Deterministic smart-grid sensor simulator (runs in the backend only).

Fleet: 20 transformers T01..T20 across 4 substations (5 each). The generator is
seeded, so the same seed + same sequence of calls yields identical readings.
It owns no threads or tasks; the pipeline decides when to call `tick()`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np

from app.schemas import AssetInfo, SensorReading
from app.simulator.scenarios import EFFECTS, Scenario, progress

NOMINAL_VOLTAGE_KV = 11.0
NOMINAL_FREQUENCY_HZ = 50.0
DIURNAL_PERIOD_TICKS = 240  # one simulated "day" in samples

_RATINGS_KVA = [1000, 1250, 1600, 2000, 2500]


def build_fleet(n_assets: int = 20, per_substation: int = 5) -> list[AssetInfo]:
    fleet: list[AssetInfo] = []
    for i in range(n_assets):
        sub = f"SS-{i // per_substation + 1:02d}"
        rating = float(_RATINGS_KVA[i % len(_RATINGS_KVA)])
        # I = S / (sqrt(3) * V) at nominal voltage
        rated_current = rating / (math.sqrt(3) * NOMINAL_VOLTAGE_KV)
        fleet.append(
            AssetInfo(
                asset_id=f"T{i + 1:02d}",
                name=f"Transformer T{i + 1:02d}",
                substation_id=sub,
                rating_kva=rating,
                rated_current_a=round(rated_current, 1),
            )
        )
    return fleet


@dataclass
class _ActiveScenario:
    scenario: Scenario
    intensity: float
    started_tick: int
    duration_ticks: Optional[int]


class GridSimulator:
    def __init__(self, seed: int = 42, ramp_ticks: int = 15, fleet: Optional[list[AssetInfo]] = None):
        self.seed = seed
        self.ramp_ticks = ramp_ticks
        self.fleet = fleet or build_fleet()
        self._rng = np.random.default_rng(seed)
        self.tick_count = 0
        self._active: dict[str, _ActiveScenario] = {}
        # per-asset persistent characteristics (drawn once, deterministic)
        self._base_load = {a.asset_id: float(self._rng.uniform(52.0, 68.0)) for a in self.fleet}
        self._phase = {a.asset_id: float(self._rng.uniform(0, 2 * math.pi)) for a in self.fleet}
        self._temp_state = {a.asset_id: 55.0 for a in self.fleet}

    # ------------------------------------------------------------------ control
    def asset_ids(self) -> list[str]:
        return [a.asset_id for a in self.fleet]

    def inject(self, asset_id: str, scenario: Scenario, intensity: float = 1.0,
               duration_ticks: Optional[int] = None) -> None:
        if asset_id not in self._base_load:
            raise KeyError(f"unknown asset {asset_id}")
        if scenario == Scenario.NORMAL:
            self._active.pop(asset_id, None)
            return
        self._active[asset_id] = _ActiveScenario(
            scenario, intensity, self.tick_count, duration_ticks
        )

    def clear(self, asset_id: Optional[str] = None) -> None:
        if asset_id is None:
            self._active.clear()
        else:
            self._active.pop(asset_id, None)

    def active_scenarios(self) -> dict[str, dict]:
        return {
            aid: {
                "scenario": s.scenario.value,
                "intensity": s.intensity,
                "age_ticks": self.tick_count - s.started_tick,
                "duration_ticks": s.duration_ticks,
            }
            for aid, s in self._active.items()
        }

    # --------------------------------------------------------------------- tick
    def tick(self, timestamp: datetime) -> list[SensorReading]:
        """Generate one reading per asset and advance the simulated clock."""
        self.tick_count += 1
        readings = [self._reading(a, timestamp) for a in self.fleet]
        # expire timed scenarios
        for aid in [k for k, s in self._active.items()
                    if s.duration_ticks is not None
                    and self.tick_count - s.started_tick >= s.duration_ticks]:
            del self._active[aid]
        return readings

    def _reading(self, asset: AssetInfo, ts: datetime) -> SensorReading:
        aid = asset.asset_id
        rng = self._rng
        t = self.tick_count

        load = (self._base_load[aid]
                + 8.0 * math.sin(2 * math.pi * t / DIURNAL_PERIOD_TICKS + self._phase[aid])
                + rng.normal(0, 1.2))

        act = self._active.get(aid)
        eff = None
        p = 0.0
        if act is not None:
            eff = EFFECTS[act.scenario]
            p = progress(t - act.started_tick, self.ramp_ticks) * act.intensity
            load += eff.load_add * p
        load = float(np.clip(load, 5.0, 200.0))

        # thermal model: first-order lag toward a load-dependent target
        target_temp = 38.0 + 0.0045 * load ** 2
        self._temp_state[aid] += 0.3 * (target_temp - self._temp_state[aid])
        temperature = self._temp_state[aid] + rng.normal(0, 0.35)

        current = asset.rated_current_a * load / 100.0 * (1 + rng.normal(0, 0.01))
        voltage = NOMINAL_VOLTAGE_KV * (1 + rng.normal(0, 0.004))
        frequency = NOMINAL_FREQUENCY_HZ + rng.normal(0, 0.02)
        vibration = 1.2 + 0.008 * load + rng.normal(0, 0.08)
        power_factor = 0.96 - 0.0003 * (load - 60.0) + rng.normal(0, 0.004)

        if eff is not None:
            temperature += eff.temp_add * p
            current *= 1 + eff.current_mult * p
            vibration += eff.vibration_add * p
            power_factor += eff.pf_add * p
            voltage *= 1 + eff.voltage_mult * p

        return SensorReading(
            timestamp=ts,
            asset_id=aid,
            substation_id=asset.substation_id,
            voltage=round(float(max(voltage, 0.0)), 4),
            current=round(float(max(current, 0.0)), 2),
            temperature=round(float(temperature), 2),
            frequency=round(float(frequency), 4),
            load_pct=round(load, 2),
            vibration=round(float(max(vibration, 0.0)), 3),
            power_factor=round(float(np.clip(power_factor, 0.0, 1.0)), 4),
        )
