"""Risk predictions and explanations."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_pipeline, require_asset
from app.pipeline import GridPipeline

router = APIRouter(prefix="/api", tags=["predictions"])


@router.get("/model/failure")
def failure_model_summary(p: GridPipeline = Depends(get_pipeline)) -> dict:
    """Expose the saved synthetic holdout evaluation and current model status."""
    report_path = Path(__file__).resolve().parents[2] / "reports" / "failure_model_metrics.json"
    report = None
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            report = None
    return {
        "available": p.failure_predictor is not None,
        "model_version": p.failure_predictor.metadata.get("model_version") if p.failure_predictor else None,
        "prediction_horizon_ticks": p.failure_predictor.metadata.get("prediction_horizon_ticks") if p.failure_predictor else None,
        "evaluation": report,
        "data_notice": "Synthetic simulator data only. Holdout metrics do not represent real-world transformer accuracy.",
    }


@router.get("/predictions")
def all_predictions(p: GridPipeline = Depends(get_pipeline)) -> list[dict]:
    return [v["assessment"].model_dump(mode="json") for v in p.latest.values()]


@router.get("/predictions/{asset_id}")
def prediction(asset_id: str, history: int = Query(0, ge=0, le=1000),
               p: GridPipeline = Depends(get_pipeline)) -> dict:
    """Latest risk assessment with explanation; `history=N` adds the last N stored assessments."""
    aid = require_asset(p, asset_id)
    cur = p.latest.get(aid)
    if cur is None:
        raise HTTPException(status_code=503, detail="No assessment yet; the simulator has not produced data.")
    out = cur["assessment"].model_dump(mode="json")
    if history:
        out["history"] = [
            {"timestamp": h.timestamp.isoformat(), "risk_score": h.risk_score,
             "risk_level": h.risk_level, "anomaly_score": h.anomaly_score,
             "failure_prediction": h.failure_prediction.model_dump(mode="json")}
            for h in p.repo.get_predictions(aid, limit=history)
        ]
    return out
