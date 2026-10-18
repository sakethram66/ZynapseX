"""ZynapseX FastAPI application.

Run:  uvicorn app.main:app --reload
Docs: http://127.0.0.1:8000/docs      WebSocket: ws://127.0.0.1:8000/ws/grid
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import alerts, assets, decisions, predictions, sensors, simulation
from app.config import Settings, get_settings
from app.database.connection import Database
from app.database.repository import Repository
from app.pipeline import GridPipeline
from app.schemas import utcnow
from app.streaming import ConnectionManager, envelope

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("zynapsex")


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.database_url)
        db.init_db()
        pipeline = GridPipeline(Repository(db), settings)
        pipeline.bootstrap()
        manager = ConnectionManager()
        app.state.db, app.state.pipeline, app.state.manager = db, pipeline, manager
        if settings.autostart_simulator:
            pipeline.start(manager.broadcast)  # the ONLY place the loop is started
            log.info("Simulator started (interval %.1fs, target=%s)",
                     settings.sample_interval_s, settings.deployment_target)
        else:
            log.info("Simulator autostart disabled")
        try:
            yield
        finally:
            await pipeline.stop()
            db.dispose()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Detect. Decide. Respond. Decision-support backend for the ZynapseX dashboard. "
                    "Data is SIMULATED; risk scores are prototype estimates, not calibrated failure probabilities.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # consistent error body: {"error": {"code": <int>, "message": <str>, ...}}
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return JSONResponse({"error": {"code": exc.status_code, "message": str(exc.detail)}},
                            status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(x) for x in e["loc"] if x != "body"), "message": e["msg"]}
                   for e in exc.errors()]
        return JSONResponse({"error": {"code": 422, "message": "Invalid request", "details": details}},
                            status_code=422)

    @app.get("/api/health", tags=["system"])
    def health(request: Request) -> dict:
        p: GridPipeline = request.app.state.pipeline
        return {
            "status": "ok",
            "time": utcnow().isoformat(),
            "simulator_running": p.running,
            "tick": p.sim.tick_count,
            "websocket_clients": request.app.state.manager.count,
            "mode": "simulated",
            "deployment_target": settings.deployment_target,
        }

    for r in (assets, sensors, alerts, predictions, decisions, simulation):
        app.include_router(r.router)

    @app.websocket("/ws/grid")
    async def grid_socket(ws: WebSocket):
        manager: ConnectionManager = ws.app.state.manager
        pipeline: GridPipeline = ws.app.state.pipeline
        await manager.connect(ws)
        try:
            await manager.send(ws, envelope("snapshot", pipeline.snapshot()))
            while True:
                text = await ws.receive_text()  # also detects client disconnects
                if text.strip().lower() == "ping":
                    await manager.send(ws, envelope("pong", {}))
        except WebSocketDisconnect:
            pass
        except Exception:
            log.exception("websocket error")
        finally:
            manager.disconnect(ws)

    return app


app = create_app()
