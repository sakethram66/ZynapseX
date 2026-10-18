import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings


def _warm(client, n=15):
    p = client.app.state.pipeline
    for _ in range(n):
        p.step()
    return p


def test_health_before_data(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["mode"] == "simulated" and body["simulator_running"] is False


def test_empty_state_is_handled(client):
    s = client.get("/api/grid/status").json()
    assert s["total_assets"] == 20 and s["assets_reporting"] == 0
    assert client.get("/api/readings/latest").json() == []
    assert client.get("/api/predictions/T01").status_code == 503
    assert client.post("/api/simulation/run", json={"scenario_type": "take_offline", "asset_id": "T17"}).status_code == 409


def test_grid_status_assets_and_detail(client):
    _warm(client)
    s = client.get("/api/grid/status").json()
    assert s["assets_reporting"] == 20 and sum(s["risk_counts"].values()) == 20
    assets = client.get("/api/assets").json()
    assert len(assets) == 20 and assets[0]["latest_reading"]["asset_id"] == "T01"
    d = client.get("/api/assets/t17").json()  # case-insensitive
    assert d["asset_id"] == "T17" and d["assessment"]["risk_level"] == "LOW" and "recommendations" in d
    assert "failure_prediction" in d["assessment"]
    assert "failure_prediction" in d["risk"]
    assert d["assessment"]["failure_prediction"]["probability"] is None


def test_failure_model_evaluation_api_and_saved_history(client):
    summary = client.get("/api/model/failure")
    assert summary.status_code == 200
    body = summary.json()
    assert body["evaluation"]["baseline"]["name"].startswith("majority class")
    assert body["evaluation"]["test_rows"] > 0 and "Synthetic" in body["data_notice"]
    _warm(client, 3)
    prediction = client.get("/api/predictions/T01", params={"history": 2}).json()
    assert len(prediction["history"]) == 2
    assert "failure_prediction" in prediction["history"][0]


def test_readings_endpoints(client):
    _warm(client)
    hist = client.get("/api/assets/T02/readings", params={"limit": 10}).json()
    assert len(hist) == 10
    assert hist[0]["timestamp"] <= hist[-1]["timestamp"]
    assert len(client.get("/api/readings/latest").json()) == 20
    assert client.get("/api/assets/T02/readings", params={"limit": 0}).status_code == 422


def test_unknown_asset_and_error_format(client):
    r = client.get("/api/assets/T99")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == 404 and "T99" in r.json()["error"]["message"]
    bad = client.post("/api/simulator/scenarios", json={"asset_id": "T01", "scenario": "nope"})
    assert bad.status_code == 422 and bad.json()["error"]["details"]


def test_scenario_injection_end_to_end(client):
    p = _warm(client, 20)
    r = client.post("/api/simulator/scenarios", json={"asset_id": "T17", "scenario": "overheating"})
    assert r.status_code == 200 and "T17" in r.json()["active"]
    for _ in range(40):
        p.step()
    pred = client.get("/api/predictions/T17", params={"history": 5}).json()
    assert pred["risk_level"] in ("HIGH", "CRITICAL")
    assert pred["contributions"][0]["factor"] == "temperature"
    assert len(pred["history"]) == 5 and "not a calibrated probability" in pred["disclaimer"].lower()
    alerts = client.get("/api/alerts", params={"asset_id": "T17", "active_only": True}).json()
    assert any(a["code"] == "TEMP_HIGH" for a in alerts)
    recs = client.get("/api/recommendations/T17").json()
    assert recs and {"asset_id", "priority", "action", "explanation", "triggering_conditions", "timestamp"} <= set(recs[0])
    assert client.get("/api/recommendations").json()[0]["priority"] in ("URGENT", "HIGH")
    assert client.get("/api/recommendations/T17/history").json()
    assert any(e["type"] == "scenario_injected" for e in client.get("/api/events").json())
    cleared = client.delete("/api/simulator/scenarios/T17").json()
    assert "T17" not in cleared["active"]


def test_scenario_listing(client):
    d = client.get("/api/simulator/scenarios").json()
    assert {s["scenario"] for s in d["available"]} >= {"normal", "overheating", "excessive_load",
                                                         "abnormal_current", "increasing_vibration", "combined_stress"}


def test_what_if_endpoint(client):
    _warm(client)
    ok = client.post("/api/simulation/run", json={"scenario_type": "take_offline", "asset_id": "T17"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["illustrative"] is True and body["verdict"] in ("ACCEPTABLE", "CAUTION", "UNSAFE")
    assert any(c["asset_id"] == "T17" and c["status_after"] == "OFFLINE" for c in body["changes"])
    assert body["assumptions"] and body["explanation"]
    assert client.post("/api/simulation/run", json={"scenario_type": "reduce_load", "asset_id": "T17"}).status_code == 422
    part = client.post("/api/simulation/run", json={"scenario_type": "reduce_load", "asset_id": "T17", "reduction_pct": 25})
    assert part.status_code == 200 and part.json()["reduction_pct"] == 25
    assert len(client.get("/api/simulation/history").json()) == 2


def test_cors_allows_configured_origin_only(client):
    ok = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


def test_websocket_snapshot_and_ping(client):
    _warm(client, 3)
    with client.websocket_connect("/ws/grid") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "snapshot" and "timestamp" in msg
        assert len(msg["data"]["assets"]) == 20 and len(msg["data"]["risks"]) == 20
        ws.send_text("ping")
        assert ws.receive_json()["type"] == "pong"


def test_websocket_streams_live_ticks_from_single_generator(tmp_path):
    """Runs the real background loop with a short interval."""
    settings = make_settings(tmp_path, sample_interval_s=0.05, autostart_simulator=True)
    with TestClient(create_app(settings)) as c:
        with c.websocket_connect("/ws/grid") as a, c.websocket_connect("/ws/grid") as b:
            assert a.receive_json()["type"] == "snapshot" and b.receive_json()["type"] == "snapshot"
            ticks = {}
            for name, ws in (("a", a), ("b", b)):
                for _ in range(40):
                    m = ws.receive_json()
                    if m["type"] == "tick":
                        ticks[name] = m
                        break
            assert set(ticks) == {"a", "b"}  # multiple clients both receive the stream
            data = ticks["a"]["data"]
            assert len(data["readings"]) == 20 and "risk_level" in data["risks"][0]
        p = c.app.state.pipeline
        t0 = p.sim.tick_count
        import time
        time.sleep(0.4)
        gained = p.sim.tick_count - t0
        assert 0 < gained <= 12  # ~8 expected at 0.05s; a duplicate generator would roughly double it
