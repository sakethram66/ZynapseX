import pytest

from app.config import get_settings
from app.ml.anomaly import get_detector
from app.ml.failure_prediction import classify, estimate_risk, stress
from app.processing.features import MODEL_FEATURES, FeatureWindow, slope
from app.simulator.generator import GridSimulator
from app.simulator.scenarios import Scenario
from tests.helpers import TS, run_scenario

S = get_settings()


def test_slope_helper():
    assert slope([1, 2, 3, 4, 5]) == pytest.approx(1.0)
    assert slope([5, 5, 5, 5]) == pytest.approx(0.0)
    assert slope([1.0, 2.0]) == 0.0  # too few samples


def test_stress_function_bands():
    ok, warn, crit = 65.0, 80.0, 95.0
    assert stress(60, ok, warn, crit) == 0.0
    assert stress(80, ok, warn, crit) == pytest.approx(0.5)
    assert stress(95, ok, warn, crit) == pytest.approx(1.0)
    assert stress(200, ok, warn, crit) == 1.0


def test_classification_boundaries():
    t = S.risk_thresholds
    assert classify(0, t) == "LOW"
    assert classify(t[0] - 0.01, t) == "LOW"
    assert classify(t[0], t) == "MEDIUM"
    assert classify(t[1], t) == "HIGH"
    assert classify(t[2], t) == "CRITICAL"
    assert classify(100, t) == "CRITICAL"


def test_normal_operation_is_low_risk_with_few_anomaly_flags():
    sim = GridSimulator(seed=7)
    fw = FeatureWindow()
    assets = {a.asset_id: a for a in sim.fleet}
    from app.ml.explainability import build_assessment
    n = flags = 0
    levels = set()
    for t in range(60):
        for r in sim.tick(TS):
            fw.push(r)
            if t >= 15:
                a = build_assessment(r, fw.features(r, assets[r.asset_id]))
                n += 1
                flags += a.is_anomaly
                levels.add(a.risk_level)
    assert levels == {"LOW"}
    assert flags / n < 0.03


@pytest.mark.parametrize("scenario", [s for s in Scenario if s != Scenario.NORMAL])
def test_every_abnormal_scenario_reaches_high_or_critical(scenario):
    a = run_scenario(scenario)[-1][2]
    assert a.risk_level in ("HIGH", "CRITICAL")
    assert a.is_anomaly


def test_strong_overload_is_critical():
    a = run_scenario(Scenario.EXCESSIVE_LOAD, intensity=1.5)[-1][2]
    assert a.risk_level == "CRITICAL"


def test_risk_is_monotonic_over_ramp():
    series = [a.risk_score for _, _, a in run_scenario(Scenario.OVERHEATING, ticks=30)]
    assert series[-1] > series[0]
    assert max(series) >= 60


def test_outputs_are_reproducible():
    a1 = run_scenario(Scenario.COMBINED_STRESS)[-1][2].model_dump(mode="json")
    a2 = run_scenario(Scenario.COMBINED_STRESS)[-1][2].model_dump(mode="json")
    assert a1 == a2


def test_anomaly_detector_normal_vs_extreme():
    det = get_detector()
    normal = {"voltage_dev_pct": 0.2, "current_ratio": 0.6, "temperature": 58, "frequency_dev_hz": 0.01,
              "load_pct": 62, "vibration": 1.7, "pf_shortfall": 0.0}
    extreme = {**normal, "temperature": 120, "vibration": 9, "load_pct": 130, "current_ratio": 1.4}
    n, e = det.score(normal), det.score(extreme)
    assert n["anomaly_score"] < 0.3 and not n["is_anomaly"]
    assert e["anomaly_score"] >= 0.9 and e["is_anomaly"]
    assert set(MODEL_FEATURES) >= {d["feature"] for d in e["top_deviations"]}
    assert det.score_many([normal, extreme])[1]["anomaly_score"] == e["anomaly_score"]


@pytest.mark.parametrize("scenario,factor", [
    (Scenario.OVERHEATING, "temperature"),
    (Scenario.EXCESSIVE_LOAD, "load_pct"),
    (Scenario.ABNORMAL_CURRENT, "current_ratio"),
    (Scenario.INCREASING_VIBRATION, "vibration"),
])
def test_explanation_names_the_real_driver_and_sums_to_score(scenario, factor):
    a = run_scenario(scenario)[-1][2]
    assert a.contributions[0].factor == factor
    pts = [c.contribution_points for c in a.contributions]
    assert pts == sorted(pts, reverse=True)
    assert sum(pts) == pytest.approx(a.risk_score, abs=0.6)  # rounding / skipped tiny terms
    assert factor.split("_")[0] in a.summary.lower() or a.contributions[0].label.lower() in a.summary.lower()
    assert "not a calibrated probability" in a.disclaimer.lower()


def test_thresholds_are_configurable():
    from dataclasses import replace
    feats = run_scenario(Scenario.OVERHEATING)[-1][1]
    strict = replace(S, limits={**S.limits, "temperature": (40.0, 50.0, 60.0)})
    loose = replace(S, limits={**S.limits, "temperature": (100.0, 120.0, 140.0)})
    assert estimate_risk(feats, 0.0, strict)["risk_score"] > estimate_risk(feats, 0.0, loose)["risk_score"]
