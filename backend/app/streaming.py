"""WebSocket connection registry. Supports many clients; drops dead ones."""
from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

from app.schemas import utcnow

log = logging.getLogger("zynapsex.ws")
SEND_TIMEOUT_S = 3.0


def envelope(type_: str, data: dict | list) -> dict:
    """Every WebSocket message uses this shape."""
    return {"type": type_, "timestamp": utcnow().isoformat(), "data": data}


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    @property
    def count(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def send(self, ws: WebSocket, message: dict) -> bool:
        try:
            await asyncio.wait_for(ws.send_json(message), SEND_TIMEOUT_S)
            return True
        except Exception:  # disconnected, slow, or closed
            self.disconnect(ws)
            return False

    async def broadcast(self, message: dict) -> None:
        if not self._clients:
            return
        await asyncio.gather(*(self.send(ws, message) for ws in list(self._clients)))
