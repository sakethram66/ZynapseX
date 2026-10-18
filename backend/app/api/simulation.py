"""Scenario injection (simulator) and what-if simulation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.deps import get_pipeline, require_asset
from app.pipeline import GridPipeline
from app.schemas import ScenarioInjectRequest, WhatIfRequest
from app.simulator.scenarios import DESCRIPTIONS, Scenario

router = APIRouter(prefix="/api", tags=["simulation"])


@router.get("/simulator/scenarios")
def list_scenarios(p: GridPipeline = Depends(get_pipeline)) -> dict:
    return {
        "available": [{"scenario": s.value, "description": DESCRIPTIONS[s]} for s in Scenario],
        "active": p.sim.active_scenarios(),
    }


@router.post("/simulator/scenarios")
async def inject_scenario(body: ScenarioInjectRequest, request: Request,
                          p: GridPipeline = Depends(get_pipeline)) -> dict:
    body.asset_id = require_asset(p, body.asset_id)
    event = p.inject(body)
    await request.app.state.manager.broadcast(event)
    return event["data"]


@router.delete("/simulator/scenarios")
async def clear_all(request: Request, p: GridPipeline = Depends(get_pipeline)) -> dict:
    event = p.clear_scenarios()
    await request.app.state.manager.broadcast(event)
    return event["data"]


@router.delete("/simulator/scenarios/{asset_id}")
async def clear_one(asset_id: str, request: Request, p: GridPipeline = Depends(get_pipeline)) -> dict:
    aid = require_asset(p, asset_id)
    event = p.clear_scenarios(aid)
    await request.app.state.manager.broadcast(event)
    return event["data"]


@router.post("/simulation/run")
def run_simulation(body: WhatIfRequest, p: GridPipeline = Depends(get_pipeline)) -> dict:
    body.asset_id = require_asset(p, body.asset_id)
    if body.scenario_type == "reduce_load" and body.reduction_pct is None:
        raise HTTPException(status_code=422, detail="reduction_pct is required for reduce_load")
    try:
        return p.what_if(body).model_dump(mode="json")
    except LookupError:
        raise HTTPException(status_code=409, detail="No live readings yet; wait for the first simulator tick.")


@router.get("/simulation/history")
def simulation_history(limit: int = Query(20, ge=1, le=200),
                       p: GridPipeline = Depends(get_pipeline)) -> list[dict]:
    return p.repo.list_simulations(limit)
