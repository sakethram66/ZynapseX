"""Explanations for a risk assessment: an exact additive breakdown of the score."""
from __future__ import annotations

from app.config import Settings, get_settings
from app.schemas import Contribution, FailurePrediction

# factor -> (label, unit)
FACTOR_META: dict[str, tuple[str, str]] = {
    "temperature": ("Winding/oil temperature", "°C"),
    "load_pct": ("Loading", "%"),
    "current_ratio": ("Current vs rated", "x rated"),
    "vibration": ("Vibration", "mm/s"),
    "voltage_dev_pct": ("Voltage deviation", "%"),
    "frequency_dev_hz": ("Frequency deviation", "Hz"),
    "pf_shortfall": ("Power-factor shortfall (vs 0.95)", ""),
    "temp_trend": ("Temperature trend", "°C/sample"),
    "vibration_trend": ("Vibration trend", "mm/s/sample"),
    "anomaly": ("Statistical anomaly", "score"),
}
MIN_POINTS = 0.1


def _detail(factor: str, value: float, stress: float, settings: Settings) -> str:
    if factor in settings.limits:
        ok, warn, crit = settings.limits[factor]
        if value <= ok:
            band = "within normal range"
        elif value <= warn:
            band = "above normal range, below warning limit"
        elif value <= crit:
            band = "above warning limit"
        else:
            band = "above critical limit"
        return f"{value:.3g} ({band}; ok≤{ok}, warn≤{warn}, crit≤{crit})"
    if factor == "temp_trend":
        ok, crit = settings.trend_limits["temp_slope"]
        return f"rising {value:.3g} °C/sample (normal≤{ok}, severe≥{crit})"
    if factor == "vibration_trend":
        ok, crit = settings.trend_limits["vibration_slope"]
        return f"rising {value:.3g} mm/s per sample (normal≤{ok}, severe≥{crit})"
    return f"anomaly score {value:.2f} (flagged at ≥0.5)"


def explain(risk: dict, features: dict[str, float], anomaly_score: float,
            settings: Settings | None = None) -> tuple[list[Contribution], str]:
    """Build ordered contributions + a one-line summary from `estimate_risk` output."""
    s = settings or get_settings()
    values = {
        **{k: features[k] for k in s.limits},
        "temp_trend": features.get("temp_slope", 0.0),
        "vibration_trend": features.get("vibration_slope", 0.0),
        "anomaly": anomaly_score,
    }
    stresses = {
        **risk["stresses"],
        "temp_trend": risk["trend_stresses"].get("temp_slope", 0.0),
        "vibration_trend": risk["trend_stresses"].get("vibration_slope", 0.0),
        "anomaly": anomaly_score,
    }
    out: list[Contribution] = []
    for factor, pts in risk["points"].items():
        if pts < MIN_POINTS:
            continue
        label, unit = FACTOR_META[factor]
        out.append(Contribution(
            factor=factor, label=label, value=round(values[factor], 4), unit=unit,
            stress=round(min(1.0, max(0.0, stresses[factor])), 4),
            contribution_points=round(pts, 2),
            detail=_detail(factor, values[factor], stresses[factor], s),
        ))
    out.sort(key=lambda c: c.contribution_points, reverse=True)

    level, score = risk["risk_level"], risk["risk_score"]
    if not out:
        summary = f"Risk {level} ({score:.0f}/100): all monitored factors are within normal ranges."
    else:
        top = ", ".join(f"{c.label.lower()} (+{c.contribution_points:.0f})" for c in out[:3])
        summary = f"Risk {level} ({score:.0f}/100). Main contributors: {top}."
    return out, summary


def build_assessment(reading, features: dict[str, float], detector=None,
                     settings: Settings | None = None, anomaly: dict | None = None,
                     failure_prediction: FailurePrediction | dict | None = None):
    """Run anomaly detection -> risk estimation -> classification -> explanation
    for one reading and return a `RiskAssessment`."""
    from app.ml.anomaly import get_detector
    from app.ml.failure_prediction import estimate_risk
    from app.schemas import RiskAssessment

    s = settings or get_settings()
    if anomaly is None:
        anomaly = (detector or get_detector()).score(features)
    risk = estimate_risk(features, anomaly["anomaly_score"], s)
    contributions, summary = explain(risk, features, anomaly["anomaly_score"], s)
    return RiskAssessment(
        asset_id=reading.asset_id,
        timestamp=reading.timestamp,
        anomaly_score=anomaly["anomaly_score"],
        is_anomaly=anomaly["is_anomaly"],
        anomaly_detail={k: v for k, v in anomaly.items() if k not in {"anomaly_score", "is_anomaly"}},
        risk_score=risk["risk_score"],
        risk_level=risk["risk_level"],
        components=risk["components"],
        trends={k: round(features.get(k, 0.0), 4) for k in ("temp_slope", "vibration_slope", "load_slope")},
        contributions=contributions,
        summary=summary,
        failure_prediction=failure_prediction or FailurePrediction(),
    )
