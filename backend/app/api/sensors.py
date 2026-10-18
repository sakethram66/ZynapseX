"""Latest and historical sensor readings."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_pipeline, require_asset
from app.pipeline import GridPipeline

router = APIRouter(prefix="/api", tags=["sensors"])


@router.get("/readings/latest")
def latest_readings(p: GridPipeline = Depends(get_pipeline)) -> list[dict]:
    return [v["reading"].model_dump(mode="json") for v in p.latest.values()]


@router.get("/assets/{asset_id}/readings")
def asset_readings(
    asset_id: str,
    limit: int = Query(100, ge=1, le=2000),
    since: Optional[datetime] = None,
    p: GridPipeline = Depends(get_pipeline),
) -> list[dict]:
    """Most recent `limit` readings, oldest first (chart-ready)."""
    aid = require_asset(p, asset_id)
    return [r.model_dump(mode="json") for r in p.repo.get_readings(aid, limit=limit, since=since)]
