"""Live session websocket fanout helpers for the Glial router."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket


class SessionLiveHub:
    """Tracks connected websocket replicas and fans out accepted changes."""

    def __init__(self) -> None:
        self._connections: dict[str, dict[str, WebSocket]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    async def register(self, session_id: str, replica_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[session_id][replica_id] = websocket

    async def unregister(self, session_id: str, replica_id: str) -> None:
        async with self._lock:
            session_connections = self._connections.get(session_id)
            if session_connections is None:
                return
            session_connections.pop(replica_id, None)
            if not session_connections:
                self._connections.pop(session_id, None)

    async def broadcast(self, session_id: str, message: dict) -> None:
        async with self._lock:
            targets = tuple(self._connections.get(session_id, {}).items())
        stale: list[str] = []
        for replica_id, websocket in targets:
            try:
                await websocket.send_json(message)
            except Exception:
                stale.append(replica_id)
        for replica_id in stale:
            await self.unregister(session_id, replica_id)
