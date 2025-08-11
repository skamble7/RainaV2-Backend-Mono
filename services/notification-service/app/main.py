# app/main.py
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from .settings import settings
from .logger import get_logger
from .websocket_manager import hub

log = get_logger("main")
app = FastAPI(title=settings.SERVICE_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.WS_ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def _startup():
    # Lazy import here so a transient error in rabbit_consumer doesn’t crash module import
    from .rabbit_consumer import consume_loop
    asyncio.create_task(consume_loop())
    log.info(f"{settings.SERVICE_NAME} started")
