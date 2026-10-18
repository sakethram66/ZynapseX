"""Pydantic schemas shared by the API, pipeline and tests."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.simulator.scenarios import Scenario

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
Severity = Literal["INFO", "WARNING", "CRITICAL"]
Priority = Literal["LOW", "MEDIUM", "HIGH", "URGENT"]

RISK_DISCLAIMER = (
    "Prototype risk estimate from transparent engineering rules on simulated data. "
    "It is NOT a calibrated probability of real equipment failure."
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SensorReading(BaseModel):
    """One validated sample. Units: voltage kV, current A, temperature degC,
    frequency Hz, load %, vibration mm/s RMS, power factor (0-1)."""

    timestamp: datetime
    asset_id: str = Field(min_length=1, max_length=16)
    substation_id: str = Field(min_length=1, max_length=16)
    voltage: float = Field(ge=0, le=100)
    current: float = Field(ge=0, le=10000)
    temperature: float = Field(ge=-40, le=250)
    frequency: float = Field(ge=40, le=70)
    load_pct: float = Field(ge=0, le=300)
    vibration: float = Field(ge=0, le=100)
    power_factor: float = Field(ge=0, le=1)

    @field_validator("timestamp")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


class AssetInfo(BaseModel):
    asset_id: str
    name: str
    substation_id: str
    rating_kva: float
    rated_current_a: float


class Contribution(BaseModel):
    factor: str
    label: str
    value: float
    unit: str
    stress: float = Field(ge=0, le=1)
    contribution_points: float
    detail: str


class FailureFeatureDriver(BaseModel):
    feature: str
    importance: float
    observed_value: float


class FailurePrediction(BaseModel):
    available: bool = False
    model_version: Optional[str] = None
    horizon_ticks: Optional[int] = None
    horizon_seconds: Optional[float] = None
    predicted_failure_within_horizon: Optional[bool] = None
    risk_classification: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL", "UNAVAILABLE"] = "UNAVAILABLE"
    model_score: Optional[float] = Field(default=None, ge=0, le=1)
    model_score_meaning: Optional[str] = None
    probability: Optional[float] = None
    probability_calibrated: bool = False
    top_features: list[FailureFeatureDriver] = Field(default_factory=list)
    message: str = "Failure prediction model is unavailable."


class RiskAssessment(BaseModel):
    asset_id: str
    timestamp: datetime
    anomaly_score: float = Field(ge=0, le=1)
    is_anomaly: bool
    anomaly_detail: dict
    risk_score: float = Field(ge=0, le=100)
    risk_level: RiskLevel
    components: dict
    trends: dict[str, float]
    contributions: list[Contribution]
    summary: str
    failure_prediction: FailurePrediction = Field(default_factory=FailurePrediction)
    disclaimer: str = RISK_DISCLAIMER


class Alert(BaseModel):
    id: Optional[int] = None
    asset_id: str
    code: str
    severity: Severity
    message: str
    value: Optional[float] = None
    threshold: Optional[float] = None
    timestamp: datetime
    resolved_at: Optional[datetime] = None


class Recommendation(BaseModel):
    id: Optional[int] = None
    asset_id: str
    priority: Priority
    action: str
    title: str
    explanation: str
    triggering_conditions: list[str]
    risk_level: RiskLevel
    timestamp: datetime


class ScenarioInjectRequest(BaseModel):
    asset_id: str
    scenario: Scenario
    intensity: float = Field(default=1.0, ge=0.1, le=2.0)
    duration_ticks: Optional[int] = Field(default=None, ge=1, le=100000)


class WhatIfRequest(BaseModel):
    scenario_type: Literal["take_offline", "reduce_load"]
    asset_id: str
    reduction_pct: Optional[float] = Field(default=None, ge=0, le=100)
    allow_cross_substation: bool = True


class AssetLoadChange(BaseModel):
    asset_id: str
    substation_id: str
    role: Literal["target", "recipient", "unaffected"]
    load_pct_before: float
    load_pct_after: float
    limit_pct: float
    status_after: Literal["OK", "CAUTION", "OVERLOAD", "OFFLINE"]


class WhatIfResult(BaseModel):
    scenario_type: str
    asset_id: str
    reduction_pct: float
    verdict: Literal["ACCEPTABLE", "CAUTION", "UNSAFE"]
    safe: bool
    changes: list[AssetLoadChange]
    violations: list[str]
    unserved_kva: float
    explanation: str
    alternatives: list[str]
    assumptions: list[str]
    illustrative: bool = True
    timestamp: datetime
