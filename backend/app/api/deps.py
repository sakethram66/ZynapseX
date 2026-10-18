"""Shared FastAPI dependencies."""
from __future__ import annotations

from fastapi import HTTPException, Request

from app.pipeline import GridPipeline


def get_pipeline(request: Request) -> GridPipeline:
    return request.app.state.pipeline


def require_asset(pipeline: GridPipeline, asset_id: str) -> str:
    asset_id = asset_id.upper()
    if asset_id not in pipeline.assets:
        raise HTTPException(status_code=404, detail=f"Unknown asset '{asset_id}'")
    return asset_id
