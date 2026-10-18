"""Abnormal-scenario definitions for the grid simulator.

Each scenario describes how a *progress* value p in [0, 1] (a linear ramp over
`scenario_ramp_ticks` samples, then held at 1) perturbs an otherwise normal
reading. The `intensity` multiplier scales every effect.

All magnitudes are illustrative simulation choices, not field data.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Scenario(str, Enum):
    NORMAL = "normal"
    OVERHEATING = "overheating"
    EXCESSIVE_LOAD = "excessive_load"
    ABNORMAL_CURRENT = "abnormal_current"
    INCREASING_VIBRATION = "increasing_vibration"
    COMBINED_STRESS = "combined_stress"


@dataclass(frozen=True)
class Effect:
    """Perturbation at full strength (p = 1, intensity = 1)."""
    temp_add: float = 0.0          # deg C added to measured temperature
    load_add: float = 0.0          # percentage points added to load
    current_mult: float = 0.0      # fractional increase of current (0.85 -> x1.85)
    vibration_add: float = 0.0     # mm/s added
    pf_add: float = 0.0            # power-factor change (negative = worse)
    voltage_mult: float = 0.0      # fractional change of voltage


EFFECTS: dict[Scenario, Effect] = {
    Scenario.NORMAL: Effect(),
    Scenario.OVERHEATING: Effect(temp_add=40.0),
    Scenario.EXCESSIVE_LOAD: Effect(load_add=38.0),
    Scenario.ABNORMAL_CURRENT: Effect(current_mult=0.85, pf_add=-0.05, voltage_mult=-0.02),
    Scenario.INCREASING_VIBRATION: Effect(vibration_add=6.0),
    Scenario.COMBINED_STRESS: Effect(
        temp_add=20.0, load_add=20.0, current_mult=0.15, vibration_add=3.0, pf_add=-0.06
    ),
}

DESCRIPTIONS: dict[Scenario, str] = {
    Scenario.NORMAL: "Normal operation (clears any injected scenario).",
    Scenario.OVERHEATING: "Transformer overheating (e.g. cooling degradation): temperature climbs.",
    Scenario.EXCESSIVE_LOAD: "Excessive load: loading rises beyond rating.",
    Scenario.ABNORMAL_CURRENT: "Abnormal current: current rises without matching load, power factor sags.",
    Scenario.INCREASING_VIBRATION: "Increasing vibration (e.g. loose core/winding): vibration trends up.",
    Scenario.COMBINED_STRESS: "Combined equipment stress: moderate heat, load, current and vibration together.",
}


def progress(age_ticks: int, ramp_ticks: int) -> float:
    """Linear ramp from 0 to 1 over `ramp_ticks`, then hold. age_ticks starts at 1."""
    if ramp_ticks <= 0:
        return 1.0
    return max(0.0, min(1.0, age_ticks / ramp_ticks))
