from fastapi import WebSocket, WebSocketDisconnect
from collections import defaultdict, deque
from typing import Dict, Set, Tuple
from .settings import settings
from .logger import get_logger

log = get_logger("ws")

class WebSocketHub:
    """
    Rooms are keyed by (tenant_id, workspace_id).
    Keeps a small per-room replay buffer.
    """
    def __init__(self):
        self.active: Dict[Tuple[str,str], Set[WebSocket]] = defaultdict(set)
        self.buffer: Dict[Tuple[str,str], deque] = defaultdict(lambda: deque(maxlen=settings.BUFFER_SIZE_PER_WORKSPACE))

    def room_key(self, tenant_id: str, workspace_id: str) -> tuple[str,str]:
        return (tenant_id or "t-unknown", workspace_id or "w-unknown")

    async def connect(self, ws: WebSocket, tenant_id: str, workspace_id: str):
        await ws.accept()
        key = self.room_key(tenant_id, workspace_id)
        self.active[key].add(ws)
        log.info(f"WS connected: {key} total={len(self.active[key])}")

    def disconnect(self, ws: WebSocket, tenant_id: str, workspace_id: str):
        key = self.room_key(tenant_id, workspace_id)
        self.active[key].discard(ws)
        log.info(f"WS disconnected: {key} total={len(self.active[key])}")

    async def send(self, tenant_id: str, workspace_id: str, message: dict):
        key = self.room_key(tenant_id, workspace_id)
        # store in replay buffer
        self.buffer[key].append(message)
        dead = []
        for ws in list(self.active[key]):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active[key].discard(ws)

    async def replay(self, ws: WebSocket, tenant_id: str, workspace_id: str):
        key = self.room_key(tenant_id, workspace_id)
        for msg in list(self.buffer[key]):
            await ws.send_json(msg)

hub = WebSocketHub()
