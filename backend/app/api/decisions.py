"""Decision-support recommendations (never executes anything)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_pipeline, require_asset
from app.decision.decision_engine import PRIORITY_ORDER
from app.pipeline import GridPipeline

router = APIRouter(prefix="/api", tags=["decisions"])


@router.get("/recommendations")
def all_recommendations(p: GridPipeline = Depends(get_pipeline)) -> list[dict]:
    """Currently active recommendations across the grid, most urgent first."""
    recs = [r for v in p.latest.values() for r in v["recommendations"]]
    recs.sort(key=lambda r: PRIORITY_ORDER[r.priority], reverse=True)
    return [r.model_dump(mode="json") for r in recs]


@router.get("/recommendations/{asset_id}")
def asset_recommendations(asset_id: str, p: GridPipeline = Depends(get_pipeline)) -> list[dict]:
    aid = require_asset(p, asset_id)
    cur = p.latest.get(aid)
    return [r.model_dump(mode="json") for r in cur["recommendations"]] if cur else []


@router.get("/recommendations/{asset_id}/history")
def recommendation_history(asset_id: str, limit: int = Query(50, ge=1, le=500),
                           p: GridPipeline = Depends(get_pipeline)) -> list[dict]:
    aid = require_asset(p, asset_id)
    return [r.model_dump(mode="json") for r in p.repo.list_recommendations(aid, limit)]
