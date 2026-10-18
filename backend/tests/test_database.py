from datetime import datetime, timedelta, timezone

from app.database.connection import Database
from app.database.repository import Repository
from app.schemas import Alert, Recommendation, ScenarioInjectRequest, WhatIfRequest
from app.simulator.generator import GridSimulator, build_fleet
from app.simulator.scenarios import Scenario
from tests.helpers import TS


def _readings(n=3):
    sim = GridSimulator(seed=1)
    return [r for i in range(n) for r in sim.tick(TS + timedelta(seconds=2 * i))]


def test_assets_roundtrip(repo):
    repo.upsert_assets(build_fleet())
    repo.upsert_assets(build_fleet())  # idempotent
    assets = repo.list_assets()
    assert len(assets) == 20 and assets[0].asset_id == "T01"


def test_readings_roundtrip_order_and_timezone(repo):
    rs = _readings(5)
    repo.add_readings(rs)
    got = repo.get_readings("T05", limit=3)
    assert len(got) == 3
    assert [g.timestamp for g in got] == sorted(g.timestamp for g in got)  # oldest -> newest
    assert got[-1].timestamp.tzinfo is not None
    assert got[-1].model_dump() == [r for r in rs if r.asset_id == "T05"][-1].model_dump()
    assert repo.latest_reading("T05").timestamp == got[-1].timestamp
    since = TS + timedelta(seconds=6)
    assert all(g.timestamp >= since for g in repo.get_readings("T05", limit=50, since=since))


def test_history_survives_restart(settings):
    db1 = Database(settings.database_url)
    db1.init_db()
    Repository(db1).add_readings(_readings(4))
    db1.dispose()
    db2 = Database(settings.database_url)  # simulates restarting the backend
    db2.init_db()
    assert len(Repository(db2).get_readings("T01", limit=10)) == 4
    db2.dispose()


def test_alert_lifecycle(repo):
    aid = repo.add_alert(Alert(asset_id="T01", code="TEMP_HIGH", severity="WARNING", message="hot",
                               value=85.0, threshold=80.0, timestamp=TS))
    assert [a.id for a in repo.list_alerts(active_only=True)] == [aid]
    repo.resolve_alert(aid, TS + timedelta(seconds=10))
    assert repo.list_alerts(active_only=True) == []
    assert repo.list_alerts(asset_id="T01")[0].resolved_at is not None


def test_prediction_roundtrip_and_recommendations_and_events(repo, pipeline):
    pipeline.step()
    a = pipeline.latest["T01"]["assessment"]
    repo.add_predictions([a])
    back = repo.latest_prediction("T01")
    assert back.risk_score == a.risk_score and back.risk_level == a.risk_level
    rid = repo.add_recommendation(Recommendation(
        asset_id="T01", priority="HIGH", action="INSPECT", title="t", explanation="e",
        triggering_conditions=["x"], risk_level="HIGH", timestamp=TS))
    recs = repo.list_recommendations("T01")
    assert recs[0].id == rid and recs[0].triggering_conditions == ["x"]
    repo.add_event("scenario_injected", "msg", TS, "T01", {"k": 1})
    assert repo.list_events()[0]["payload"] == {"k": 1}


def test_simulation_history(repo, pipeline):
    pipeline.step()
    req = WhatIfRequest(scenario_type="take_offline", asset_id="T17")
    pipeline.what_if(req)
    hist = repo.list_simulations()
    assert len(hist) == 1 and hist[0]["request"]["asset_id"] == "T17"
    assert hist[0]["result"]["illustrative"] is True


def test_retention_prunes_old_rows(repo):
    for i in range(5):
        repo.add_readings(_readings(1))
    assert repo.count_readings() == 100
    removed = repo.prune(readings_keep_total=40, predictions_keep_total=40)
    assert removed["readings"] == 60
    assert repo.count_readings() == 40
