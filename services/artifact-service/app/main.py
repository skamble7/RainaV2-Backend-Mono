# services/artifact-service/app/main.py
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .logging_conf import configure_logging
from .routers.artifact_routes import router as artifact_router
from .db.mongodb import get_db
from .dal import artifact_dal
from .events.workspace_consumer import run_workspace_created_consumer
from .config import settings

# NEW: correlation IDs middleware + logging filter
from .middleware.correlation import CorrelationIdMiddleware, CorrelationIdFilter

configure_logging()
log = logging.getLogger(__name__)

# Attach correlation filter to key loggers (root + uvicorn)
_corr_filter = CorrelationIdFilter()
for name in ("", "uvicorn.access", "uvicorn.error", __name__.split(".")[0] or "app"):
    logging.getLogger(name).addFilter(_corr_filter)

# Background task handles
_shutdown_event: asyncio.Event | None = None
_consumer_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup:
      - init Mongo indexes
      - start workspace.created consumer
    Shutdown:
      - stop consumer gracefully
    """
    global _shutdown_event, _consumer_task

    db = await get_db()
    await artifact_dal.ensure_indexes(db)
    log.info("Mongo indexes ensured")

    _shutdown_event = asyncio.Event()
    _consumer_task = asyncio.create_task(run_workspace_created_consumer(db, _shutdown_event))
    log.info("workspace.created consumer started")

    try:
        yield
    finally:
        if _shutdown_event:
            _shutdown_event.set()
        if _consumer_task:
            _consumer_task.cancel()
            try:
                await _consumer_task
            except Exception:
                pass
        log.info("Artifact service shutdown complete")


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

# NEW: add correlation middleware so every request/response carries IDs
app.add_middleware(CorrelationIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    # Explicitly allow correlation headers (["*"] generally covers this, but being explicit helps in some setups)
    allow_headers=["*", "x-request-id", "x-correlation-id"],
    expose_headers=["x-request-id", "x-correlation-id"],
)

# Routers
app.include_router(artifact_router)


# Optional: simple health probe
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
