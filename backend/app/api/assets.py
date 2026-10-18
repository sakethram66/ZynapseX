"""Grid overview, asset list and asset detail."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_pipeline, require_asset
from app.pipeline import GridPipeline

router = APIRouter(prefix="/api", tags=["assets"])


@router.get("/grid/status")
def grid_status(p: GridPipeline = Depends(get_pipeline)) -> dict:
    return p.status()


@router.get("/assets")
def list_assets(p: GridPipeline = Depends(get_pipeline)) -> list[dict]:
    return [p.asset_summary(a.asset_id) for a in p.fleet]


@router.get("/assets/{asset_id}")
def asset_detail(asset_id: str, p: GridPipeline = Depends(get_pipeline)) -> dict:
    aid = require_asset(p, asset_id)
    cur = p.latest.get(aid)
    detail = p.asset_summary(aid)
    detail["assessment"] = cur["assessment"].model_dump(mode="json") if cur else None
    detail["recommendations"] = [r.model_dump(mode="json") for r in cur["recommendations"]] if cur else []
    detail["active_alerts"] = [a.model_dump(mode="json")
                               for a in p.repo.list_alerts(asset_id=aid, active_only=True)]
    return detail
