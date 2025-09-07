#services/workspace-service/app/main.py
import logging
import uvicorn
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app.routers.workspace_routes import router as workspace_router
from app.config import settings
from app.logging_conf import *  # configure root logger
from app.db.mongodb import close_db
from app.events.rabbit import close as close_rabbit
from app.middleware.correlation import (
    CorrelationIdMiddleware,
    CorrelationIdFilter,
)

# Build app
app = FastAPI(
    title="RAINA – Workspace Service",
    version="0.1.0",
    default_response_class=ORJSONResponse,
)

# Correlation-ID middleware (adds x-request-id/x-correlation-id)
app.add_middleware(CorrelationIdMiddleware)

# Ensure all major loggers include request/correlation IDs
_corr_filter = CorrelationIdFilter()
for logger_name in ("", "uvicorn.access", "uvicorn.error", "app"):
    logging.getLogger(logger_name).addFilter(_corr_filter)

# Routes
app.include_router(workspace_router)

@app.get("/healthz")
async def health():
    return {"status": "ok", "service": settings.SERVICE_NAME}

@app.on_event("shutdown")
async def shutdown_event():
    await close_db()
    await close_rabbit()

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True,
    )
