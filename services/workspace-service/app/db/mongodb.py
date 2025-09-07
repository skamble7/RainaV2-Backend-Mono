# services/workspace-service/app/db/mongodb.py
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config import settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None

async def get_db() -> AsyncIOMotorDatabase:
    global _client, _db
    if _db is None:
        # Motor/pymongo handles mongodb+srv Atlas URIs and TLS automatically
        _client = AsyncIOMotorClient(settings.MONGO_URI)
        _db = _client[settings.MONGO_DB]
    return _db

async def close_db():
    global _client
    if _client:
        _client.close()
        _client = None
