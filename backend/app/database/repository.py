"""All database reads/writes. Returns pydantic schema objects / plain dicts."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import delete, func, select

from app.database.connection import Database
from app.database.models import (
    AlertRow, AssetRow, EventRow, PredictionRow, ReadingRow, RecommendationRow, SimulationRow,
)
from app.schemas import (
    Alert, AssetInfo, Recommendation, RiskAssessment, SensorReading, WhatIfRequest, WhatIfResult,
)


def to_db(dt: datetime) -> datetime:
    """aware -> naive UTC (naive input is assumed to already be UTC)."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def from_db(dt: Optional[datetime]) -> Optional[datetime]:
    return None if dt is None else dt.replace(tzinfo=timezone.utc)


class Repository:
    def __init__(self, db: Database):
        self.db = db

    # ---------------------------------------------------------------- assets
    def upsert_assets(self, assets: Iterable[AssetInfo]) -> None:
        with self.db.session() as s:
            for a in assets:
                s.merge(AssetRow(**a.model_dump()))

    def list_assets(self) -> list[AssetInfo]:
        with self.db.session() as s:
            rows = s.scalars(select(AssetRow).order_by(AssetRow.asset_id)).all()
            return [AssetInfo(asset_id=r.asset_id, name=r.name, substation_id=r.substation_id,
                              rating_kva=r.rating_kva, rated_current_a=r.rated_current_a) for r in rows]

    # -------------------------------------------------------------- readings
    @staticmethod
    def _reading(r: ReadingRow) -> SensorReading:
        return SensorReading(
            timestamp=from_db(r.ts), asset_id=r.asset_id, substation_id=r.substation_id,
            voltage=r.voltage, current=r.current, temperature=r.temperature, frequency=r.frequency,
            load_pct=r.load_pct, vibration=r.vibration, power_factor=r.power_factor,
        )

    def add_readings(self, readings: Iterable[SensorReading]) -> None:
        with self.db.session() as s:
            s.add_all([
                ReadingRow(ts=to_db(r.timestamp), asset_id=r.asset_id, substation_id=r.substation_id,
                           voltage=r.voltage, current=r.current, temperature=r.temperature,
                           frequency=r.frequency, load_pct=r.load_pct, vibration=r.vibration,
                           power_factor=r.power_factor)
                for r in readings
            ])

    def get_readings(self, asset_id: str, limit: int = 100, since: Optional[datetime] = None) -> list[SensorReading]:
        """Most recent `limit` readings, returned oldest -> newest."""
        with self.db.session() as s:
            q = select(ReadingRow).where(ReadingRow.asset_id == asset_id)
            if since is not None:
                q = q.where(ReadingRow.ts >= to_db(since))
            rows = s.scalars(q.order_by(ReadingRow.id.desc()).limit(limit)).all()
            return [self._reading(r) for r in reversed(rows)]

    def latest_reading(self, asset_id: str) -> Optional[SensorReading]:
        rs = self.get_readings(asset_id, limit=1)
        return rs[0] if rs else None

    def count_readings(self) -> int:
        with self.db.session() as s:
            return int(s.scalar(select(func.count()).select_from(ReadingRow)) or 0)

    # ----------------------------------------------------------- predictions
    def add_predictions(self, items: Iterable[RiskAssessment]) -> None:
        with self.db.session() as s:
            s.add_all([
                PredictionRow(ts=to_db(p.timestamp), asset_id=p.asset_id, risk_score=p.risk_score,
                              risk_level=p.risk_level, anomaly_score=p.anomaly_score,
                              is_anomaly=p.is_anomaly, payload=p.model_dump(mode="json"))
                for p in items
            ])

    def get_predictions(self, asset_id: str, limit: int = 50) -> list[RiskAssessment]:
        with self.db.session() as s:
            rows = s.scalars(select(PredictionRow).where(PredictionRow.asset_id == asset_id)
                             .order_by(PredictionRow.id.desc()).limit(limit)).all()
            return [RiskAssessment.model_validate(r.payload) for r in reversed(rows)]

    def latest_prediction(self, asset_id: str) -> Optional[RiskAssessment]:
        ps = self.get_predictions(asset_id, limit=1)
        return ps[0] if ps else None

    # ---------------------------------------------------------------- alerts
    @staticmethod
    def _alert(r: AlertRow) -> Alert:
        return Alert(id=r.id, asset_id=r.asset_id, code=r.code, severity=r.severity, message=r.message,
                     value=r.value, threshold=r.threshold, timestamp=from_db(r.ts),
                     resolved_at=from_db(r.resolved_at))

    def add_alert(self, a: Alert) -> int:
        with self.db.session() as s:
            row = AlertRow(ts=to_db(a.timestamp), asset_id=a.asset_id, code=a.code, severity=a.severity,
                           message=a.message, value=a.value, threshold=a.threshold)
            s.add(row)
            s.flush()
            return row.id

    def resolve_alert(self, alert_id: int, when: datetime) -> None:
        with self.db.session() as s:
            row = s.get(AlertRow, alert_id)
            if row is not None and row.resolved_at is None:
                row.resolved_at = to_db(when)

    def list_alerts(self, asset_id: Optional[str] = None, active_only: bool = False,
                    limit: int = 100) -> list[Alert]:
        with self.db.session() as s:
            q = select(AlertRow)
            if asset_id:
                q = q.where(AlertRow.asset_id == asset_id)
            if active_only:
                q = q.where(AlertRow.resolved_at.is_(None))
            rows = s.scalars(q.order_by(AlertRow.id.desc()).limit(limit)).all()
            return [self._alert(r) for r in rows]

    # -------------------------------------------------------- recommendations
    def add_recommendation(self, r: Recommendation) -> int:
        with self.db.session() as s:
            row = RecommendationRow(
                ts=to_db(r.timestamp), asset_id=r.asset_id, priority=r.priority, action=r.action,
                title=r.title, explanation=r.explanation,
                triggering_conditions=list(r.triggering_conditions), risk_level=r.risk_level)
            s.add(row)
            s.flush()
            return row.id

    def list_recommendations(self, asset_id: Optional[str] = None, limit: int = 50) -> list[Recommendation]:
        with self.db.session() as s:
            q = select(RecommendationRow)
            if asset_id:
                q = q.where(RecommendationRow.asset_id == asset_id)
            rows = s.scalars(q.order_by(RecommendationRow.id.desc()).limit(limit)).all()
            return [Recommendation(id=r.id, asset_id=r.asset_id, priority=r.priority, action=r.action,
                                   title=r.title, explanation=r.explanation,
                                   triggering_conditions=list(r.triggering_conditions),
                                   risk_level=r.risk_level, timestamp=from_db(r.ts)) for r in rows]

    # ------------------------------------------------------------ simulations
    def add_simulation(self, req: WhatIfRequest, result: WhatIfResult) -> int:
        with self.db.session() as s:
            row = SimulationRow(ts=to_db(result.timestamp), scenario_type=result.scenario_type,
                                asset_id=result.asset_id, verdict=result.verdict,
                                request=req.model_dump(mode="json"), result=result.model_dump(mode="json"))
            s.add(row)
            s.flush()
            return row.id

    def list_simulations(self, limit: int = 20) -> list[dict]:
        with self.db.session() as s:
            rows = s.scalars(select(SimulationRow).order_by(SimulationRow.id.desc()).limit(limit)).all()
            return [{"id": r.id, "timestamp": from_db(r.ts).isoformat(), "request": r.request,
                     "result": r.result} for r in rows]

    # ----------------------------------------------------------------- events
    def add_event(self, type_: str, message: str, ts: datetime, asset_id: Optional[str] = None,
                  payload: Optional[dict] = None) -> None:
        with self.db.session() as s:
            s.add(EventRow(ts=to_db(ts), type=type_, asset_id=asset_id, message=message, payload=payload))

    def list_events(self, limit: int = 100, asset_id: Optional[str] = None) -> list[dict]:
        with self.db.session() as s:
            q = select(EventRow)
            if asset_id:
                q = q.where(EventRow.asset_id == asset_id)
            rows = s.scalars(q.order_by(EventRow.id.desc()).limit(limit)).all()
            return [{"id": r.id, "timestamp": from_db(r.ts).isoformat(), "type": r.type,
                     "asset_id": r.asset_id, "message": r.message, "payload": r.payload} for r in rows]

    # -------------------------------------------------------------- retention
    def prune(self, readings_keep_total: int, predictions_keep_total: int) -> dict[str, int]:
        """Keep only the newest N rows of the two high-frequency tables."""
        removed = {}
        with self.db.session() as s:
            for model, keep, name in ((ReadingRow, readings_keep_total, "readings"),
                                      (PredictionRow, predictions_keep_total, "predictions")):
                max_id = s.scalar(select(func.max(model.id)))
                if max_id is None:
                    removed[name] = 0
                    continue
                res = s.execute(delete(model).where(model.id <= max_id - keep))
                removed[name] = res.rowcount or 0
        return removed
