from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from .logging_conf import configure_logging
from .routers.capability_routes import router as capability_router
from .db.mongodb import get_db
from .dal.capability_dal import ensure_indexes
from .config import settings
from .middleware.correlation import CorrelationIdMiddleware, CorrelationIdFilter

# Configure structured/central logging first
configure_logging()

# Create app
app = FastAPI(title=settings.app_name, version="0.1.0")

# CORS (expose correlation headers so callers can read them)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-request-id", "x-correlation-id"],
)

# Correlation-ID middleware (adds x-request-id/x-correlation-id to context + response)
app.add_middleware(CorrelationIdMiddleware)

# Attach correlation filter to key loggers so every line carries IDs
_corr_filter = CorrelationIdFilter()
for logger_name in ("", "uvicorn.access", "uvicorn.error", "app"):
    logging.getLogger(logger_name).addFilter(_corr_filter)

@app.get("/health")
async def health():
    db = await get_db()
    await db.command("ping")
    return {"status": "ok"}

@app.on_event("startup")
async def on_startup():
    db = await get_db()
    await ensure_indexes(db)

# Routes
app.include_router(capability_router)
