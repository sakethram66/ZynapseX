import pytest

from app.schemas import WhatIfRequest
from app.simulation.what_if import run_what_if
from app.simulator.generator import build_fleet

ASSETS = {a.asset_id: a for a in build_fleet()}


def loads(value=60.0, **over):
    d = {k: value for k in ASSETS}
    d.update(over)
    return d


def kva(l):
    return sum(l[k] / 100 * ASSETS[k].rating_kva for k in l)


def test_take_offline_with_headroom_is_acceptable_and_conserves_load():
    before = loads(55.0, T17=70.0)
    snapshot = dict(before)
    res = run_what_if(WhatIfRequest(scenario_type="take_offline", asset_id="T17"), before, ASSETS)
    assert before == snapshot  # input untouched
    assert res.verdict == "ACCEPTABLE" and res.safe and res.illustrative
    after = {c.asset_id: c.load_pct_after for c in res.changes}
    assert after["T17"] == 0.0
    t = next(c for c in res.changes if c.asset_id == "T17")
    assert t.status_after == "OFFLINE" and t.role == "target"
    full = {k: after.get(k, before[k]) for k in before}
    assert kva(full) == pytest.approx(kva(before), rel=1e-3)
    assert res.assumptions and res.explanation


def test_same_substation_is_preferred():
    res = run_what_if(WhatIfRequest(scenario_type="take_offline", asset_id="T17"), loads(50.0, T17=60.0), ASSETS)
    recips = {c.asset_id for c in res.changes if c.role == "recipient"}
    assert recips and all(ASSETS[a].substation_id == ASSETS["T17"].substation_id for a in recips)


def test_overloaded_neighbours_make_it_unsafe_with_alternatives():
    l = loads(99.0, T17=80.0)
    res = run_what_if(WhatIfRequest(scenario_type="take_offline", asset_id="T17"), l, ASSETS)
    assert res.verdict == "UNSAFE" and not res.safe
    assert res.unserved_kva > 0 and res.violations
    assert res.alternatives


def test_cross_substation_flag_changes_outcome():
    l = loads(40.0, T17=95.0, T16=97.0, T18=97.0, T19=97.0, T20=97.0)
    on = run_what_if(WhatIfRequest(scenario_type="take_offline", asset_id="T17"), l, ASSETS)
    off = run_what_if(WhatIfRequest(scenario_type="take_offline", asset_id="T17", allow_cross_substation=False), l, ASSETS)
    assert on.unserved_kva < off.unserved_kva
    assert off.verdict == "UNSAFE"
    assert any("cross-substation" in a.lower() for a in off.alternatives)


def test_reduce_load_partial_and_partial_alternative():
    l = loads(60.0, T17=100.0)
    res = run_what_if(WhatIfRequest(scenario_type="reduce_load", asset_id="T17", reduction_pct=30), l, ASSETS)
    t = next(c for c in res.changes if c.asset_id == "T17")
    assert t.load_pct_after == pytest.approx(70.0, abs=0.01)
    assert res.reduction_pct == 30
    tight = loads(97.0, T17=100.0)
    bad = run_what_if(WhatIfRequest(scenario_type="reduce_load", asset_id="T17", reduction_pct=100), tight, ASSETS)
    assert bad.verdict in ("UNSAFE", "CAUTION")
    assert any("instead of" in a for a in bad.alternatives)


def test_critical_risk_assets_are_not_used_as_recipients():
    res = run_what_if(WhatIfRequest(scenario_type="take_offline", asset_id="T17"), loads(40.0, T17=70.0), ASSETS,
                      risk_levels={"T16": "CRITICAL"})
    assert "T16" not in {c.asset_id for c in res.changes if c.role == "recipient"}
    assert "T16" in res.explanation  # excluded assets are named in the explanation


def test_configurable_limit_changes_verdict():
    from dataclasses import replace
    from app.config import get_settings
    l = loads(70.0, T17=90.0)
    req = WhatIfRequest(scenario_type="take_offline", asset_id="T17")
    assert run_what_if(req, l, ASSETS, settings=replace(get_settings(), sim_load_limit_pct=100.0)).safe
    assert not run_what_if(req, l, ASSETS, settings=replace(get_settings(), sim_load_limit_pct=72.0, sim_caution_pct=70.0)).safe


def test_errors():
    with pytest.raises(KeyError):
        run_what_if(WhatIfRequest(scenario_type="take_offline", asset_id="T99"), loads(), ASSETS)
    with pytest.raises(ValueError):
        run_what_if(WhatIfRequest(scenario_type="reduce_load", asset_id="T17"), loads(), ASSETS)
