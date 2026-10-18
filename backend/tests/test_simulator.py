from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas import SensorReading
from app.simulator.generator import GridSimulator, build_fleet
from app.simulator.scenarios import Scenario
from tests.helpers import TS


def _collect(sim, n):
    return [r for _ in range(n) for r in sim.tick(TS)]


def test_fleet_has_t01_to_t20_across_substations():
    fleet = build_fleet()
    assert [a.asset_id for a in fleet] == [f"T{i:02d}" for i in range(1, 21)]
    assert len({a.substation_id for a in fleet}) == 4
    assert all(a.rating_kva > 0 and a.rated_current_a > 0 for a in fleet)


def test_tick_returns_one_valid_reading_per_asset():
    sim = GridSimulator(seed=1)
    readings = sim.tick(TS)
    assert len(readings) == 20
    assert len({r.asset_id for r in readings}) == 20
    for r in readings:
        assert isinstance(r, SensorReading)
        assert r.timestamp.tzinfo is not None
        assert r.substation_id.startswith("SS-")


def test_same_seed_is_reproducible_and_different_seed_differs():
    a = [r.model_dump() for r in _collect(GridSimulator(seed=5), 10)]
    b = [r.model_dump() for r in _collect(GridSimulator(seed=5), 10)]
    c = [r.model_dump() for r in _collect(GridSimulator(seed=6), 10)]
    assert a == b
    assert a != c


def test_normal_operation_stays_in_plausible_bounds():
    for r in _collect(GridSimulator(seed=3), 120):
        assert 30 <= r.load_pct <= 90
        assert 45 <= r.temperature <= 78
        assert r.vibration < 3.2
        assert r.power_factor > 0.92
        assert 49.8 < r.frequency < 50.2
        assert 10.6 < r.voltage < 11.4


def _final(scenario, asset="T05", ticks=30, intensity=1.0):
    sim = GridSimulator(seed=11)
    _collect(sim, 20)
    sim.inject(asset, scenario, intensity)
    base = next(r for r in _collect(GridSimulator(seed=11), 20 + ticks)[-20:] if r.asset_id == asset)
    last = next(r for r in _collect(sim, ticks)[-20:] if r.asset_id == asset)
    return base, last


def test_overheating_raises_temperature():
    base, last = _final(Scenario.OVERHEATING)
    assert last.temperature > base.temperature + 25


def test_excessive_load_raises_load_and_current():
    base, last = _final(Scenario.EXCESSIVE_LOAD)
    assert last.load_pct > base.load_pct + 25
    assert last.current > base.current * 1.3


def test_abnormal_current_raises_current_without_load_change():
    base, last = _final(Scenario.ABNORMAL_CURRENT)
    assert last.current > base.current * 1.5
    assert abs(last.load_pct - base.load_pct) < 8


def test_increasing_vibration_raises_vibration():
    base, last = _final(Scenario.INCREASING_VIBRATION)
    assert last.vibration > base.vibration + 4


def test_combined_stress_moves_several_metrics():
    base, last = _final(Scenario.COMBINED_STRESS)
    assert last.temperature > base.temperature + 10
    assert last.load_pct > base.load_pct + 10
    assert last.vibration > base.vibration + 2


def test_scenario_ramps_gradually():
    sim = GridSimulator(seed=2, ramp_ticks=20)
    _collect(sim, 10)
    sim.inject("T01", Scenario.INCREASING_VIBRATION)
    series = [next(r for r in sim.tick(TS) if r.asset_id == "T01").vibration for _ in range(25)]
    assert series[-1] > series[0] + 3
    assert series[10] > series[2]


def test_inject_clear_expire_and_unknown_asset():
    sim = GridSimulator(seed=1)
    sim.inject("T02", Scenario.OVERHEATING, duration_ticks=3)
    assert "T02" in sim.active_scenarios()
    _collect(sim, 3)
    assert "T02" not in sim.active_scenarios()
    sim.inject("T03", Scenario.OVERHEATING)
    sim.inject("T03", Scenario.NORMAL)
    assert sim.active_scenarios() == {}
    sim.inject("T04", Scenario.EXCESSIVE_LOAD)
    sim.clear()
    assert sim.active_scenarios() == {}
    with pytest.raises(KeyError):
        sim.inject("T99", Scenario.OVERHEATING)


def test_reading_validation_rejects_bad_values():
    good = dict(timestamp=TS, asset_id="T01", substation_id="SS-01", voltage=11.0, current=50.0,
                temperature=60.0, frequency=50.0, load_pct=60.0, vibration=1.5, power_factor=0.95)
    SensorReading(**good)
    for field, bad in [("voltage", -1), ("power_factor", 1.5), ("frequency", 10), ("temperature", 999),
                       ("load_pct", -5), ("vibration", -0.1)]:
        with pytest.raises(ValidationError):
            SensorReading(**{**good, field: bad})
    with pytest.raises(ValidationError):
        SensorReading(**{k: v for k, v in good.items() if k != "asset_id"})


def test_naive_timestamp_is_made_utc_aware():
    r = SensorReading(timestamp=datetime(2026, 1, 1), asset_id="T01", substation_id="SS-01", voltage=11.0,
                      current=1.0, temperature=50.0, frequency=50.0, load_pct=50.0, vibration=1.0,
                      power_factor=0.9)
    assert r.timestamp.tzinfo is not None
