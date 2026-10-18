from datetime import timedelta

from app.schemas import ScenarioInjectRequest
from app.simulator.scenarios import Scenario
from tests.helpers import TS


def _steps(p, n):
    out = []
    for i in range(n):
        out += p.step(TS + timedelta(seconds=2 * i))
    return out


def test_step_emits_tick_with_expected_shape_and_persists(pipeline, repo):
    events = pipeline.step(TS)
    tick = events[0]
    assert tick["type"] == "tick" and "timestamp" in tick
    d = tick["data"]
    assert len(d["readings"]) == 20 and len(d["risks"]) == 20
    assert {"asset_id", "voltage", "current", "temperature", "frequency", "load_pct", "vibration",
            "power_factor", "substation_id", "timestamp"} <= set(d["readings"][0])
    assert {"risk_score", "risk_level", "contributions", "summary", "disclaimer"} <= set(d["risks"][0])
    assert d["status"]["total_assets"] == 20 and d["status"]["assets_reporting"] == 20
    assert repo.count_readings() == 20


def test_normal_grid_raises_no_alerts(pipeline, repo):
    _steps(pipeline, 40)
    assert repo.list_alerts() == []
    assert pipeline.status()["risk_counts"]["LOW"] == 20


def test_injected_scenario_raises_alerts_recommendations_and_timeline(pipeline, repo):
    _steps(pipeline, 20)
    ev = pipeline.inject(ScenarioInjectRequest(asset_id="T17", scenario=Scenario.OVERHEATING))
    assert ev["type"] == "scenario" and "T17" in ev["data"]["active"]
    events = _steps(pipeline, 40)
    kinds = {e["type"] for e in events}
    assert {"alert", "recommendation"} <= kinds
    alerts = repo.list_alerts(asset_id="T17")
    assert any(a.code == "TEMP_HIGH" for a in alerts)
    assert all(a.asset_id == "T17" for a in repo.list_alerts() if a.severity != "INFO")
    assert any(r.action in ("INSPECT", "INSPECT_URGENT") for r in repo.list_recommendations("T17"))
    assert any(e["type"] == "scenario_injected" for e in repo.list_events())
    assert pipeline.latest["T17"]["assessment"].risk_level in ("HIGH", "CRITICAL")
    assert pipeline.latest["T01"]["assessment"].risk_level == "LOW"


def test_alerts_are_not_duplicated_while_condition_persists(pipeline, repo):
    _steps(pipeline, 20)
    pipeline.inject(ScenarioInjectRequest(asset_id="T03", scenario=Scenario.INCREASING_VIBRATION))
    _steps(pipeline, 60)
    keys = [(a.code, a.severity) for a in repo.list_alerts(asset_id="T03")]
    assert len(keys) == len(set(keys))


def test_clearing_scenario_resolves_alerts(pipeline, repo):
    _steps(pipeline, 20)
    pipeline.inject(ScenarioInjectRequest(asset_id="T05", scenario=Scenario.EXCESSIVE_LOAD, intensity=1.5))
    _steps(pipeline, 40)
    assert repo.list_alerts(asset_id="T05", active_only=True)
    pipeline.clear_scenarios("T05")
    _steps(pipeline, 80)
    assert repo.list_alerts(asset_id="T05", active_only=True) == []


def test_what_if_uses_live_state_and_requires_data(pipeline):
    import pytest
    from app.schemas import WhatIfRequest
    with pytest.raises(LookupError):
        pipeline.what_if(WhatIfRequest(scenario_type="take_offline", asset_id="T17"))
    pipeline.step(TS)
    res = pipeline.what_if(WhatIfRequest(scenario_type="take_offline", asset_id="T17"))
    live = pipeline.latest["T17"]["reading"].load_pct
    t = next(c for c in res.changes if c.asset_id == "T17")
    assert t.load_pct_before == round(live, 2)
    assert pipeline.latest["T17"]["reading"].load_pct == live  # simulation did not modify live state


def test_restart_warms_window_from_history(settings):
    from app.database.connection import Database
    from app.database.repository import Repository
    from app.pipeline import GridPipeline
    db = Database(settings.database_url); db.init_db()
    p1 = GridPipeline(Repository(db), settings); p1.bootstrap()
    _steps(p1, 12)
    p2 = GridPipeline(Repository(db), settings); p2.bootstrap()
    assert len(p2.window.history("T01")) == 12
    db.dispose()
