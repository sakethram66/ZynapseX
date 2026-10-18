"""SQLAlchemy table definitions. All timestamps are stored as naive UTC and
converted back to timezone-aware UTC by the repository."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AssetRow(Base):
    __tablename__ = "assets"
    asset_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    substation_id: Mapped[str] = mapped_column(String(16), index=True)
    rating_kva: Mapped[float] = mapped_column(Float)
    rated_current_a: Mapped[float] = mapped_column(Float)


class ReadingRow(Base):
    __tablename__ = "sensor_readings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    asset_id: Mapped[str] = mapped_column(String(16))
    substation_id: Mapped[str] = mapped_column(String(16))
    voltage: Mapped[float] = mapped_column(Float)
    current: Mapped[float] = mapped_column(Float)
    temperature: Mapped[float] = mapped_column(Float)
    frequency: Mapped[float] = mapped_column(Float)
    load_pct: Mapped[float] = mapped_column(Float)
    vibration: Mapped[float] = mapped_column(Float)
    power_factor: Mapped[float] = mapped_column(Float)
    __table_args__ = (Index("ix_readings_asset_id_id", "asset_id", "id"),)


class PredictionRow(Base):
    __tablename__ = "risk_predictions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    asset_id: Mapped[str] = mapped_column(String(16))
    risk_score: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(16))
    anomaly_score: Mapped[float] = mapped_column(Float)
    is_anomaly: Mapped[bool] = mapped_column(Boolean)
    payload: Mapped[dict] = mapped_column(JSON)  # full RiskAssessment JSON
    __table_args__ = (Index("ix_predictions_asset_id_id", "asset_id", "id"),)


class AlertRow(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    asset_id: Mapped[str] = mapped_column(String(16), index=True)
    code: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class RecommendationRow(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    asset_id: Mapped[str] = mapped_column(String(16), index=True)
    priority: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(48))
    title: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    triggering_conditions: Mapped[list] = mapped_column(JSON)
    risk_level: Mapped[str] = mapped_column(String(16))


class SimulationRow(Base):
    __tablename__ = "simulation_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    scenario_type: Mapped[str] = mapped_column(String(32))
    asset_id: Mapped[str] = mapped_column(String(16))
    verdict: Mapped[str] = mapped_column(String(16))
    request: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)


class EventRow(Base):
    """Timeline of notable events (scenario injected/cleared, alert raised/resolved)."""
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    type: Mapped[str] = mapped_column(String(32))
    asset_id: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
