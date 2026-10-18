import pytest

from app.simulator.scenarios import Scenario
from app.decision.decision_engine import ACTIONS, PRIORITY_ORDER, generate_recommendations
from tests.helpers import run_scenario


def _recs(scenario, intensity=1.0):
    r, f, a = run_scenario(scenario, intensity)[-1]
    return generate_recommendations(r, a, f), a


def test_normal_operation_yields_no_actionable_recommendations():
    recs, a = _recs(Scenario.NORMAL)
    assert a.risk_level == "LOW"
    assert all(r.action == "INCREASE_MONITORING" and r.priority == "LOW" for r in recs)


def test_critical_asset_gets_urgent_inspection_and_what_if():
    recs, a = _recs(Scenario.EXCESSIVE_LOAD, 1.5)
    actions = {r.action for r in recs}
    assert a.risk_level == "CRITICAL"
    assert {"INSPECT_URGENT", "REDUCE_LOAD", "EVALUATE_LOAD_DISTRIBUTION", "RUN_WHAT_IF",
            "INCREASE_MONITORING"} <= actions
    assert recs[0].priority == "URGENT"


def test_vibration_triggers_mechanical_inspection():
    recs, _ = _recs(Scenario.INCREASING_VIBRATION)
    assert "INSPECT_MECHANICAL" in {r.action for r in recs}


def test_current_without_load_triggers_electrical_inspection():
    recs, _ = _recs(Scenario.ABNORMAL_CURRENT)
    assert "INSPECT_ELECTRICAL" in {r.action for r in recs}
    assert "REDUCE_LOAD" not in {r.action for r in recs}


def test_every_recommendation_is_complete_and_grounded():
    recs, a = _recs(Scenario.COMBINED_STRESS)
    assert recs
    for r in recs:
        assert r.asset_id == "T17"
        assert r.action in ACTIONS
        assert r.priority in PRIORITY_ORDER
        assert r.explanation and r.triggering_conditions
        assert r.timestamp is not None
        assert "decision support only" in r.explanation.lower()
    assert any(f"{a.risk_score:.0f}" in c for r in recs for c in r.triggering_conditions)


def test_sorted_by_priority():
    recs, _ = _recs(Scenario.COMBINED_STRESS)
    ranks = [PRIORITY_ORDER[r.priority] for r in recs]
    assert ranks == sorted(ranks, reverse=True)
