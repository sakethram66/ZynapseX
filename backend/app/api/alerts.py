"""Alerts and the event timeline."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_pipeline, require_asset
from app.pipeline import GridPipeline

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts")
def list_alerts(
    asset_id: Optional[str] = None,
    active_only: bool = False,
    limit: int = Query(100, ge=1, le=1000),
    p: GridPipeline = Depends(get_pipeline),
) -> list[dict]:
    aid = require_asset(p, asset_id) if asset_id else None
    return [a.model_dump(mode="json") for a in p.repo.list_alerts(aid, active_only, limit)]


@router.get("/events")
def list_events(
    asset_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    p: GridPipeline = Depends(get_pipeline),
) -> list[dict]:
    aid = require_asset(p, asset_id) if asset_id else None
    return p.repo.list_events(limit=limit, asset_id=aid)
