"""Rule-based decision SUPPORT. Never actuates real equipment.

Rules consume the live reading, derived features, anomaly output and risk
result, and emit structured recommendations. Every recommendation lists the
concrete triggering conditions (with the values that fired them).
"""
from __future__ import annotations

from datetime import datetime

from app.config import Settings, get_settings
from app.ml.failure_prediction import metric_stresses, trend_stresses
from app.schemas import Recommendation, RiskAssessment, SensorReading

PRIORITY_ORDER = {"URGENT": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}
LEVEL_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

ACTIONS = (
    "INSPECT_URGENT", "INSPECT", "INSPECT_MECHANICAL", "INSPECT_ELECTRICAL",
    "REDUCE_LOAD", "EVALUATE_LOAD_DISTRIBUTION", "INCREASE_MONITORING", "RUN_WHAT_IF",
)

NOTICE = "Decision support only: nothing here controls real equipment or switching."


def _limit_text(factor: str, value: float, settings: Settings, unit: str = "") -> str:
    ok, warn, crit = settings.limits[factor]
    if value > crit:
        rel = f"above critical limit {crit}{unit}"
    elif value > warn:
        rel = f"above warning limit {warn}{unit}"
    elif value > ok:
        rel = f"above normal range ({ok}{unit})"
    else:
        rel = "normal"
    return f"{factor}={value:.3g}{unit} ({rel})"


def generate_recommendations(
    reading: SensorReading,
    assessment: RiskAssessment,
    features: dict[str, float],
    settings: Settings | None = None,
    now: datetime | None = None,
) -> list[Recommendation]:
    s = settings or get_settings()
    ts = now or reading.timestamp
    aid = reading.asset_id
    level = assessment.risk_level
    lvl = LEVEL_ORDER[level]
    stresses = metric_stresses(features, s)
    trends = trend_stresses(features, s)
    risk_cond = f"risk_score={assessment.risk_score:.0f}/100 ({level})"

    recs: list[Recommendation] = []

    def add(priority: str, action: str, title: str, explanation: str, conds: list[str]) -> None:
        recs.append(Recommendation(
            asset_id=aid, priority=priority, action=action, title=title,
            explanation=f"{explanation} {NOTICE}", triggering_conditions=conds,
            risk_level=level, timestamp=ts,
        ))

    # R1/R2: inspection driven by overall risk
    top = assessment.contributions[0].label.lower() if assessment.contributions else "multiple factors"
    if level == "CRITICAL":
        add("URGENT", "INSPECT_URGENT", f"Inspect {aid} as soon as possible",
            f"Prototype risk index is CRITICAL, driven mainly by {top}.", [risk_cond])
    elif level == "HIGH":
        add("HIGH", "INSPECT", f"Schedule an inspection of {aid}",
            f"Prototype risk index is HIGH, driven mainly by {top}.", [risk_cond])

    # R3/R4: load reduction and redistribution
    load = features["load_pct"]
    ok_l, warn_l, crit_l = s.limits["load_pct"]
    heat_loaded = stresses["temperature"] >= s.alert_stress_warn and load > ok_l
    if load > warn_l or heat_loaded:
        conds = [_limit_text("load_pct", load, s, "%")]
        if heat_loaded:
            conds.append(_limit_text("temperature", features["temperature"], s, "°C"))
        prio = "URGENT" if load > crit_l else ("HIGH" if lvl >= 2 else "MEDIUM")
        add(prio, "REDUCE_LOAD", f"Reduce the simulated load on {aid}",
            "Loading and/or temperature are elevated; lowering load reduces thermal and electrical stress.",
            conds)
        add("HIGH" if lvl >= 2 else "MEDIUM", "EVALUATE_LOAD_DISTRIBUTION",
            f"Evaluate alternative load distribution for {aid}",
            "Check whether neighbouring transformers have headroom to take part of this load.",
            conds)

    # R5: mechanical
    if stresses["vibration"] >= s.alert_stress_warn or trends["vibration_slope"] >= 0.3:
        conds = [_limit_text("vibration", features["vibration"], s, " mm/s")]
        if trends["vibration_slope"] >= 0.3:
            conds.append(f"vibration trend +{features['vibration_slope']:.3g} mm/s per sample")
        add("HIGH" if stresses["vibration"] >= s.alert_stress_crit else "MEDIUM", "INSPECT_MECHANICAL",
            f"Inspect {aid} for mechanical looseness",
            "Vibration is elevated or rising, which can indicate loose core, winding or mounting.",
            conds)

    # R8: current not explained by load
    if stresses["current_ratio"] >= s.alert_stress_warn and stresses["load_pct"] < 0.3:
        add("HIGH", "INSPECT_ELECTRICAL", f"Inspect {aid} electrical connections and phase balance",
            "Current is high relative to rating while reported loading is not, which may indicate a "
            "metering, connection or phase issue.",
            [_limit_text("current_ratio", features["current_ratio"], s, "x"),
             _limit_text("load_pct", load, s, "%")])

    # R6: monitoring
    watch: list[str] = []
    if lvl >= 1:
        watch.append(risk_cond)
    if assessment.is_anomaly:
        watch.append(f"anomaly_score={assessment.anomaly_score:.2f} (>=0.5)")
    for k, v in trends.items():
        if v >= 0.3:
            watch.append(f"{k}={features[k]:.3g}/sample (trend stress {v:.2f})")
    if watch:
        add("MEDIUM" if lvl >= 1 else "LOW", "INCREASE_MONITORING",
            f"Increase monitoring frequency for {aid}",
            "Readings are deviating from normal; sample this asset more often until it settles.",
            watch)

    # R7: what-if
    if lvl >= 2 or any(r.action == "REDUCE_LOAD" for r in recs):
        add("MEDIUM", "RUN_WHAT_IF", f"Run a what-if simulation for {aid}",
            f"Test taking {aid} offline or reducing its load to see whether neighbours can absorb it.",
            [risk_cond])

    recs.sort(key=lambda r: PRIORITY_ORDER[r.priority], reverse=True)
    return recs
