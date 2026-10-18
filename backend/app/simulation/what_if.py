"""What-if simulation: illustrative load redistribution. Pure function, no side effects.

ASSUMPTIONS (also returned in every result):
  * There is NO real network topology or power-flow model. Load moved away from
    the target is shifted to other transformers as kVA (load% x rating).
  * Recipients are taken from the same substation first; other substations are
    used only if `allow_cross_substation` is true (assumes tie capacity exists).
  * Recipients with CRITICAL risk are excluded as recipients.
  * Each recipient may be filled up to the configured load limit
    (default 100 % of rating); transfers are proportional to available headroom.
  * "reduce_load" shifts the chosen percentage of the target's load to others
    (it is not shed). "take_offline" is reduce_load with 100 %.
  * Voltage, losses, thermal inertia and protection behaviour are ignored.
Results are illustrative; they never modify real equipment or stored readings.
"""
from __future__ import annotations

import math
from datetime import datetime

from app.config import Settings, get_settings
from app.schemas import AssetInfo, AssetLoadChange, WhatIfRequest, WhatIfResult, utcnow

ASSUMPTIONS = [
    "Illustrative simplified load redistribution; no real network topology or power-flow is modelled.",
    "Moved load is shifted to other transformers in kVA (load % x rating), same substation first.",
    "Cross-substation transfers (if allowed) assume tie capacity exists.",
    "Transformers with CRITICAL risk are not used as recipients.",
    "Recipients are filled proportionally to headroom, up to the configured load limit.",
    "Voltage, losses, thermal inertia and protection behaviour are ignored.",
]


def _status(load_pct: float, limit: float, caution: float, offline: bool = False) -> str:
    if offline:
        return "OFFLINE"
    if load_pct > limit + 1e-9:
        return "OVERLOAD"
    if load_pct > caution:
        return "CAUTION"
    return "OK"


def _fill(kva_needed: float, pool: list[str], loads: dict[str, float],
          assets: dict[str, AssetInfo], limit: float) -> tuple[dict[str, float], float]:
    """Distribute kVA over `pool` proportionally to headroom. Returns (alloc_kva, leftover_kva)."""
    head = {a: max(0.0, limit - loads[a]) / 100.0 * assets[a].rating_kva for a in pool}
    total = sum(head.values())
    if total <= 0 or kva_needed <= 0:
        return {}, max(kva_needed, 0.0)
    take = min(kva_needed, total)
    alloc = {a: take * h / total for a, h in head.items() if h > 0}
    return alloc, kva_needed - take


def run_what_if(
    req: WhatIfRequest,
    loads: dict[str, float],
    assets: dict[str, AssetInfo],
    risk_levels: dict[str, str] | None = None,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> WhatIfResult:
    """`loads` = current load % per asset (a snapshot; not modified)."""
    s = settings or get_settings()
    limit, caution = s.sim_load_limit_pct, s.sim_caution_pct
    risk_levels = risk_levels or {}
    if req.asset_id not in assets or req.asset_id not in loads:
        raise KeyError(req.asset_id)
    if req.scenario_type == "reduce_load" and req.reduction_pct is None:
        raise ValueError("reduction_pct is required for reduce_load")

    reduction = 100.0 if req.scenario_type == "take_offline" else float(req.reduction_pct)
    target = assets[req.asset_id]
    target_before = loads[target.asset_id]
    move_kva = target_before / 100.0 * target.rating_kva * reduction / 100.0

    others = [a for a in assets if a != target.asset_id]
    eligible = [a for a in others if risk_levels.get(a) != "CRITICAL"]
    excluded = [a for a in others if a not in eligible]
    same_sub = [a for a in eligible if assets[a].substation_id == target.substation_id]
    other_sub = [a for a in eligible if assets[a].substation_id != target.substation_id]

    alloc1, left = _fill(move_kva, same_sub, loads, assets, limit)
    alloc2: dict[str, float] = {}
    if req.allow_cross_substation:
        alloc2, left = _fill(left, other_sub, loads, assets, limit)
    alloc = {**alloc1, **alloc2}

    # alternatives need headroom figures
    head_same = sum(max(0.0, limit - loads[a]) / 100 * assets[a].rating_kva for a in same_sub)
    head_cross = sum(max(0.0, limit - loads[a]) / 100 * assets[a].rating_kva for a in other_sub)

    after: dict[str, float] = dict(loads)
    target_after = target_before * (1 - reduction / 100.0)
    after[target.asset_id] = target_after
    for a, kva in alloc.items():
        after[a] = loads[a] + kva / assets[a].rating_kva * 100.0

    changes: list[AssetLoadChange] = []
    for aid, info in assets.items():
        if aid == target.asset_id:
            offline = req.scenario_type == "take_offline"
            role, status = "target", _status(after[aid], limit, caution, offline)
            shown_after = 0.0 if offline else after[aid]
        elif aid in alloc:
            role, status, shown_after = "recipient", _status(after[aid], limit, caution), after[aid]
        else:
            if abs(after[aid] - loads[aid]) < 1e-9 and aid not in alloc:
                continue  # unaffected assets are omitted to keep payloads small
            role, status, shown_after = "unaffected", _status(after[aid], limit, caution), after[aid]
        changes.append(AssetLoadChange(
            asset_id=aid, substation_id=info.substation_id, role=role,
            load_pct_before=round(loads[aid], 2), load_pct_after=round(shown_after, 2),
            limit_pct=limit, status_after=status,
        ))

    violations: list[str] = []
    if left > 1e-6:
        violations.append(
            f"{left:.0f} kVA of {target.asset_id}'s moved load cannot be placed within the "
            f"{limit:.0f}% limit of the available recipients."
        )
    for c in changes:
        if c.status_after == "OVERLOAD":
            violations.append(f"{c.asset_id} would be at {c.load_pct_after:.1f}% (limit {limit:.0f}%).")
    cautions = [c for c in changes if c.role == "recipient" and c.status_after == "CAUTION"]

    if violations:
        verdict = "UNSAFE"
    elif cautions:
        verdict = "CAUTION"
    else:
        verdict = "ACCEPTABLE"

    action = (f"taking {target.asset_id} offline" if req.scenario_type == "take_offline"
              else f"reducing {target.asset_id}'s load by {reduction:.0f}%")
    Action = action[0].upper() + action[1:]
    n_rec = len(alloc)
    if verdict == "ACCEPTABLE":
        explanation = (f"{Action} moves about {move_kva:.0f} kVA to "
                       f"{n_rec} other transformer(s); all stay within the {limit:.0f}% limit "
                       f"and below the {caution:.0f}% caution level.")
    elif verdict == "CAUTION":
        names = ", ".join(f"{c.asset_id} ({c.load_pct_after:.0f}%)" for c in cautions)
        explanation = (f"{Action} is feasible within the {limit:.0f}% limit, "
                       f"but leaves recipients above the {caution:.0f}% caution level: {names}.")
    else:
        explanation = (f"{Action} is potentially unsafe in this simplified "
                       f"model: " + " ".join(violations))
    if excluded:
        explanation += f" (Excluded as recipients due to CRITICAL risk: {', '.join(excluded)}.)"

    alternatives: list[str] = []
    if verdict != "ACCEPTABLE":
        usable = head_same + (head_cross if req.allow_cross_substation else 0.0)
        full_kva = target_before / 100.0 * target.rating_kva
        if full_kva > 0 and usable > 0:
            max_pct = math.floor(min(100.0, usable / full_kva * 100.0))
            if 0 < max_pct < reduction:
                alternatives.append(
                    f"Reduce {target.asset_id} by about {max_pct}% instead of {reduction:.0f}% "
                    f"to keep recipients within the limit."
                )
        if not req.allow_cross_substation and head_cross > 0:
            alternatives.append(
                f"Allow cross-substation transfer: about {head_cross:.0f} kVA of extra headroom exists elsewhere."
            )
        if left > 1e-6:
            alternatives.append(
                f"Defer or curtail roughly {left:.0f} kVA of non-critical load, or arrange temporary capacity."
            )
        alternatives.append("Stage the transfer in smaller steps and re-run this simulation after each step.")

    return WhatIfResult(
        scenario_type=req.scenario_type, asset_id=target.asset_id, reduction_pct=reduction,
        verdict=verdict, safe=(verdict != "UNSAFE"), changes=changes, violations=violations,
        unserved_kva=round(max(left, 0.0), 2), explanation=explanation, alternatives=alternatives,
        assumptions=ASSUMPTIONS, illustrative=True, timestamp=now or utcnow(),
    )
