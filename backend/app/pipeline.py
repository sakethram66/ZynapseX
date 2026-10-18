"""The single streaming pipeline:

  simulator tick -> feature engineering -> anomaly detection -> risk estimation
  -> classification -> explanation -> alerts + recommendations -> persistence
  -> WebSocket broadcast

Exactly one `GridPipeline` exists per app (created in the FastAPI lifespan) and
it owns exactly one background task, so generators cannot be duplicated.
`step()` is synchronous and deterministic (given the seed), which is what the
tests call directly.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime
from typing import Awaitable, Callable, Optional

from app.config import Settings
from app.database.repository import Repository
from app.decision.decision_engine import PRIORITY_ORDER, generate_recommendations
from app.ml.anomaly import get_detector
from app.ml.explainability import build_assessment
from app.ml.failure_prediction import get_failure_predictor, metric_stresses
from app.processing.features import FeatureWindow
from app.schemas import (
    Alert, AssetInfo, FailurePrediction, Recommendation, RiskAssessment, ScenarioInjectRequest, SensorReading,
    WhatIfRequest, WhatIfResult, utcnow,
)
from app.simulation.what_if import run_what_if
from app.simulator.generator import GridSimulator, build_fleet
from app.simulator.scenarios import Scenario
from app.streaming import envelope

log = logging.getLogger("zynapsex.pipeline")

SEVERITY_RANK = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}
LEVEL_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
ANOMALY_STREAK_TO_ALERT = 3
FAILURE_STREAK_TO_ALERT = 3
FAILURE_CLEAR_STREAK_TO_RESOLVE = 3
HYSTERESIS = 0.9  # an active metric alert clears only below 90 % of its warn stress

METRIC_ALERTS = {
    "temperature": ("TEMP_HIGH", "Temperature", "°C"),
    "load_pct": ("LOAD_HIGH", "Loading", "%"),
    "current_ratio": ("CURRENT_HIGH", "Current vs rated", "x"),
    "vibration": ("VIBRATION_HIGH", "Vibration", " mm/s"),
    "voltage_dev_pct": ("VOLTAGE_DEVIATION", "Voltage deviation", "%"),
    "frequency_dev_hz": ("FREQUENCY_DEVIATION", "Frequency deviation", " Hz"),
    "pf_shortfall": ("PF_LOW", "Power-factor shortfall", ""),
}

Broadcast = Callable[[dict], Awaitable[None]]


class GridPipeline:
    def __init__(self, repo: Repository, settings: Settings, detector=None, failure_predictor=None):
        self.repo = repo
        self.settings = settings
        self.fleet: list[AssetInfo] = build_fleet()
        self.assets = {a.asset_id: a for a in self.fleet}
        self.sim = GridSimulator(seed=settings.simulator_seed, ramp_ticks=settings.scenario_ramp_ticks,
                                 fleet=self.fleet)
        self.window = FeatureWindow(settings.window_size)
        self.detector = detector or get_detector()
        self.failure_predictor = failure_predictor if failure_predictor is not None else get_failure_predictor()
        self.latest: dict[str, dict] = {}
        self.last_tick_at: Optional[datetime] = None
        self._active_alerts: dict[tuple[str, str], tuple[str, int]] = {}
        self._anomaly_streak: dict[str, int] = {}
        self._failure_streak: dict[str, int] = {}
        self._failure_clear_streak: dict[str, int] = {}
        self._rec_state: dict[tuple[str, str], tuple[int, int]] = {}  # -> (tick, priority rank)
        self._lock = threading.RLock()
        self._task: Optional[asyncio.Task] = None
        self.running = False

    # --------------------------------------------------------------- startup
    def bootstrap(self) -> None:
        """Persist the asset list, warm the rolling window from stored history,
        and close alerts left open by a previous run."""
        self.repo.upsert_assets(self.fleet)
        for a in self.fleet:
            for r in self.repo.get_readings(a.asset_id, limit=self.settings.window_size):
                self.window.push(r)
        now = utcnow()
        for alert in self.repo.list_alerts(active_only=True, limit=1000):
            self.repo.resolve_alert(alert.id, now)

    # ------------------------------------------------------------------ step
    def step(self, now: Optional[datetime] = None) -> list[dict]:
        """Generate one sample per asset and run the full pipeline.
        Returns WebSocket messages (tick first, then alert/recommendation events)."""
        with self._lock:
            now = now or utcnow()
            readings = self.sim.tick(now)
            tick = self.sim.tick_count

            feats: dict[str, dict] = {}
            for r in readings:
                self.window.push(r)
                feats[r.asset_id] = self.window.features(r, self.assets[r.asset_id])

            anomalies = self.detector.score_many([feats[r.asset_id] for r in readings])
            failure_predictions = [FailurePrediction() for _ in readings]
            if self.failure_predictor is not None:
                model_rows = [{
                    "temperature": r.temperature, "voltage": r.voltage, "current": r.current,
                    "load_pct": r.load_pct, "frequency": r.frequency, "vibration": r.vibration,
                    "power_factor": r.power_factor,
                    "temp_slope": feats[r.asset_id]["temp_slope"],
                    "vibration_slope": feats[r.asset_id]["vibration_slope"],
                    "load_slope": feats[r.asset_id]["load_slope"],
                    "rating_kva": self.assets[r.asset_id].rating_kva,
                    "rated_current_a": self.assets[r.asset_id].rated_current_a,
                } for r in readings]
                try:
                    failure_predictions = self.failure_predictor.predict_many(
                        model_rows, self.settings.sample_interval_s,
                        self.settings.failure_score_thresholds)
                except Exception:
                    log.exception("Failure prediction inference failed; preserving the rest of the pipeline")
                    failure_predictions = [FailurePrediction(message="Failure model inference failed.")
                                           for _ in readings]
            assessments: list[RiskAssessment] = []
            events: list[dict] = []
            new_alerts: list[Alert] = []
            new_recs: list[Recommendation] = []

            for r, an, failure_prediction in zip(readings, anomalies, failure_predictions):
                f = feats[r.asset_id]
                a = build_assessment(r, f, settings=self.settings, anomaly=an,
                                     failure_prediction=failure_prediction)
                assessments.append(a)
                recs = generate_recommendations(r, a, f, self.settings, now)
                self.latest[r.asset_id] = {"reading": r, "assessment": a, "recommendations": recs}
                new_alerts += self._update_alerts(r, f, a, now)
                new_recs += self._persist_new_recs(recs, tick)

            self.last_tick_at = now
            self.repo.add_readings(readings)
            self.repo.add_predictions(assessments)
            if tick % self.settings.prune_every_n_ticks == 0:
                n = len(self.fleet)
                self.repo.prune(self.settings.readings_keep_per_asset * n,
                                self.settings.predictions_keep_per_asset * n)

            events.append(envelope("tick", {
                "tick": tick,
                "readings": [r.model_dump(mode="json") for r in readings],
                "risks": [a.model_dump(mode="json") for a in assessments],
                "status": self.status(),
            }))
            events += [envelope("alert", a.model_dump(mode="json")) for a in new_alerts]
            events += [envelope("recommendation", r.model_dump(mode="json")) for r in new_recs]
            return events

    # ---------------------------------------------------------------- alerts
    def _candidates(self, r: SensorReading, f: dict, a: RiskAssessment) -> dict[str, tuple]:
        """code -> (severity, message, value, threshold); severity None = not firing."""
        s = self.settings
        aid = r.asset_id
        stresses = metric_stresses(f, s)
        out: dict[str, tuple] = {}
        for factor, (code, label, unit) in METRIC_ALERTS.items():
            st = stresses[factor]
            ok, warn, crit = s.limits[factor]
            key = (aid, code)
            active = key in self._active_alerts
            if st >= s.alert_stress_crit:
                sev, thr, word = "CRITICAL", crit, "critical limit"
            elif st >= s.alert_stress_warn:
                sev, thr, word = "WARNING", warn, "warning limit"
            elif active and st >= s.alert_stress_warn * HYSTERESIS:
                sev, thr, word = self._active_alerts[key][0], warn, "warning limit"
            else:
                continue
            out[code] = (sev, f"{label} {f[factor]:.3g}{unit} is at/above the {word} ({thr}{unit}).",
                         round(f[factor], 4), thr)
        if a.risk_level in ("HIGH", "CRITICAL"):
            sev = "CRITICAL" if a.risk_level == "CRITICAL" else "WARNING"
            out["RISK_HIGH"] = (sev, f"Risk level {a.risk_level} ({a.risk_score:.0f}/100). {a.summary}",
                                a.risk_score, s.risk_thresholds[1 if a.risk_level == "HIGH" else 2])
        model_flag = (a.failure_prediction.available
                      and a.failure_prediction.predicted_failure_within_horizon)
        active_failure = (aid, "FAILURE_HORIZON") in self._active_alerts
        self._failure_streak[aid] = self._failure_streak.get(aid, 0) + 1 if model_flag else 0
        self._failure_clear_streak[aid] = 0 if model_flag else self._failure_clear_streak.get(aid, 0) + 1
        if model_flag and (active_failure or self._failure_streak[aid] >= FAILURE_STREAK_TO_ALERT):
            horizon = a.failure_prediction.horizon_ticks
            out["FAILURE_HORIZON"] = (
                "WARNING",
                f"Synthetic-trained failure classifier flags {aid} within {horizon} simulator ticks; verify with an inspection.",
                None, None,
            )
        elif active_failure and self._failure_clear_streak[aid] < FAILURE_CLEAR_STREAK_TO_RESOLVE:
            out["FAILURE_HORIZON"] = (
                "WARNING", f"Monitoring the recent synthetic failure-model flag for {aid}.", None, None,
            )
        streak = self._anomaly_streak.get(aid, 0) + 1 if a.is_anomaly else 0
        self._anomaly_streak[aid] = streak
        if streak >= ANOMALY_STREAK_TO_ALERT or (("ANOMALY" in {c for (x, c) in self._active_alerts if x == aid})
                                                  and a.is_anomaly):
            out["ANOMALY"] = ("INFO", f"Sustained statistical anomaly (score {a.anomaly_score:.2f}).",
                              a.anomaly_score, 0.5)
        return out

    def _update_alerts(self, r: SensorReading, f: dict, a: RiskAssessment, now: datetime) -> list[Alert]:
        aid = r.asset_id
        cands = self._candidates(r, f, a)
        created: list[Alert] = []
        for code, (sev, msg, val, thr) in cands.items():
            key = (aid, code)
            cur = self._active_alerts.get(key)
            if cur is not None and SEVERITY_RANK[sev] <= SEVERITY_RANK[cur[0]]:
                continue  # already alerting at this severity or higher
            if cur is not None:  # escalation: close old, open new
                self.repo.resolve_alert(cur[1], now)
            alert = Alert(asset_id=aid, code=code, severity=sev, message=msg, value=val,
                          threshold=thr, timestamp=now)
            alert.id = self.repo.add_alert(alert)
            self._active_alerts[key] = (sev, alert.id)
            self.repo.add_event("alert_raised", f"{aid}: {msg}", now, aid, {"code": code, "severity": sev})
            created.append(alert)
        for key in [k for k in self._active_alerts if k[0] == aid and k[1] not in cands]:
            _, alert_id = self._active_alerts.pop(key)
            self.repo.resolve_alert(alert_id, now)
            self.repo.add_event("alert_resolved", f"{aid}: {key[1]} cleared", now, aid, {"code": key[1]})
        return created

    # -------------------------------------------------------- recommendations
    def _persist_new_recs(self, recs: list[Recommendation], tick: int) -> list[Recommendation]:
        """Store a recommendation when it is new, escalated, or past its cooldown."""
        fresh: list[Recommendation] = []
        for rec in recs:
            key = (rec.asset_id, rec.action)
            rank = PRIORITY_ORDER[rec.priority]
            prev = self._rec_state.get(key)
            if (prev is None or rank > prev[1]
                    or tick - prev[0] >= self.settings.recommendation_cooldown_ticks):
                rec.id = self.repo.add_recommendation(rec)
                self._rec_state[key] = (tick, rank)
                fresh.append(rec)
        return fresh

    # ------------------------------------------------------------- scenarios
    def inject(self, req: ScenarioInjectRequest) -> dict:
        with self._lock:
            if req.asset_id not in self.assets:
                raise KeyError(req.asset_id)
            now = utcnow()
            self.sim.inject(req.asset_id, req.scenario, req.intensity, req.duration_ticks)
            if req.scenario == Scenario.NORMAL:
                msg, type_ = f"Scenario cleared on {req.asset_id}", "scenario_cleared"
            else:
                msg, type_ = (f"Scenario '{req.scenario.value}' injected on {req.asset_id} "
                              f"(intensity {req.intensity})"), "scenario_injected"
            self.repo.add_event(type_, msg, now, req.asset_id, req.model_dump(mode="json"))
            return envelope("scenario", {"event": type_, "message": msg, "active": self.sim.active_scenarios()})

    def clear_scenarios(self, asset_id: Optional[str] = None) -> dict:
        with self._lock:
            if asset_id is not None and asset_id not in self.assets:
                raise KeyError(asset_id)
            self.sim.clear(asset_id)
            msg = f"Scenario cleared on {asset_id}" if asset_id else "All scenarios cleared"
            self.repo.add_event("scenario_cleared", msg, utcnow(), asset_id)
            return envelope("scenario", {"event": "scenario_cleared", "message": msg,
                                         "active": self.sim.active_scenarios()})

    # --------------------------------------------------------------- queries
    def what_if(self, req: WhatIfRequest) -> WhatIfResult:
        with self._lock:
            if req.asset_id not in self.assets:
                raise KeyError(req.asset_id)
            if not self.latest:
                raise LookupError("no readings yet")
            loads = {k: v["reading"].load_pct for k, v in self.latest.items()}
            levels = {k: v["assessment"].risk_level for k, v in self.latest.items()}
        result = run_what_if(req, loads, self.assets, levels, self.settings)
        self.repo.add_simulation(req, result)
        return result

    def asset_summary(self, asset_id: str) -> dict:
        info = self.assets[asset_id]
        cur = self.latest.get(asset_id)
        return {
            **info.model_dump(),
            "latest_reading": cur["reading"].model_dump(mode="json") if cur else None,
            "risk": ({"risk_score": cur["assessment"].risk_score, "risk_level": cur["assessment"].risk_level,
                      "anomaly_score": cur["assessment"].anomaly_score,
                      "is_anomaly": cur["assessment"].is_anomaly,
                      "failure_prediction": cur["assessment"].failure_prediction.model_dump(mode="json"),
                      "summary": cur["assessment"].summary}
                     if cur else None),
            "active_scenario": self.sim.active_scenarios().get(asset_id),
        }

    def status(self) -> dict:
        levels = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        loads = []
        for v in self.latest.values():
            levels[v["assessment"].risk_level] += 1
            loads.append(v["reading"].load_pct)
        return {
            "mode": "simulated",
            "deployment_target": self.settings.deployment_target,
            "simulator_running": self.running,
            "tick": self.sim.tick_count,
            "sample_interval_s": self.settings.sample_interval_s,
            "last_update": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "total_assets": len(self.fleet),
            "substations": len({a.substation_id for a in self.fleet}),
            "assets_reporting": len(self.latest),
            "risk_counts": levels,
            "anomalies": sum(1 for v in self.latest.values() if v["assessment"].is_anomaly),
            "active_alerts": len(self._active_alerts),
            "average_load_pct": round(sum(loads) / len(loads), 2) if loads else None,
            "active_scenarios": self.sim.active_scenarios(),
        }

    def snapshot(self) -> dict:
        """Full current state, sent to each new WebSocket client."""
        with self._lock:
            return {
                "status": self.status(),
                "assets": [self.asset_summary(a.asset_id) for a in self.fleet],
                "readings": [v["reading"].model_dump(mode="json") for v in self.latest.values()],
                "risks": [v["assessment"].model_dump(mode="json") for v in self.latest.values()],
            }

    # ------------------------------------------------------------- lifecycle
    async def run(self, broadcast: Broadcast) -> None:
        interval = self.settings.sample_interval_s
        self.running = True
        try:
            while True:
                started = time.monotonic()
                try:
                    events = await asyncio.to_thread(self.step)
                    for ev in events:
                        await broadcast(ev)
                except Exception:  # keep the stream alive; surface in logs
                    log.exception("pipeline step failed")
                await asyncio.sleep(max(0.0, interval - (time.monotonic() - started)))
        finally:
            self.running = False

    def start(self, broadcast: Broadcast) -> None:
        """Start the one background loop (no-op if already running)."""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self.run(broadcast), name="zynapsex-pipeline")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
