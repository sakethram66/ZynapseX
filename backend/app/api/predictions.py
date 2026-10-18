"""Risk predictions and explanations."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_pipeline, require_asset
from app.pipeline import GridPipeline

router = APIRouter(prefix="/api", tags=["predictions"])


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
             "risk_level": h.risk_level, "anomaly_score": h.anomaly_score}
            for h in p.repo.get_predictions(aid, limit=history)
        ]
    return out
