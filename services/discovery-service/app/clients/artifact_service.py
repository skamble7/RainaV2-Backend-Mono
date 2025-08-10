import httpx
from app.config import settings

async def create_artifact(workspace_id: str, artifact: dict) -> dict:
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S) as client:
        r = await client.post(f"{settings.ARTIFACT_SERVICE_URL}/artifact/{workspace_id}", json=artifact)
        if r.is_error:
            # Return rich error so caller can log status/message
            raise httpx.HTTPStatusError(f"{r.status_code}: {r.text}", request=r.request, response=r)
        return r.json()

async def head_artifact(workspace_id: str, artifact_id: str) -> str | None:
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S) as client:
        r = await client.head(f"{settings.ARTIFACT_SERVICE_URL}/artifact/{workspace_id}/{artifact_id}")
        return r.headers.get("ETag")
