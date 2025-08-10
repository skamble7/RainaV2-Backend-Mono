from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .logging_conf import configure_logging
from .routers.capability_routes import router as capability_router
from .db.mongodb import get_db
from .dal.capability_dal import ensure_indexes
from .config import settings

configure_logging()
app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

@app.get("/health")
async def health():
    db = await get_db()
    await db.command("ping")
    return {"status": "ok"}

@app.on_event("startup")
async def on_startup():
    db = await get_db()
    await ensure_indexes(db)

app.include_router(capability_router)
