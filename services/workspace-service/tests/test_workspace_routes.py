import anyio
from httpx import AsyncClient
from app.main import app

async def test_health():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        res = await ac.get("/healthz")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"