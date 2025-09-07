# app/db/mongodb.py
from __future__ import annotations
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from app.config import settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None

def get_db() -> AsyncIOMotorDatabase:
    global _client, _db
    if _db is None:
        _client = AsyncIOMotorClient(settings.MONGODB_URI)
        _db = _client[settings.MONGODB_DB]
    return _db

def get_collection(name: str) -> AsyncIOMotorCollection:
    return get_db()[name]
