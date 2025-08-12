import httpx
import uuid
from typing import Optional
from app.config import settings

# Pull IDs from middleware if present (falls back to fresh UUIDs)
try:
    from app.middleware.correlation import request_id_var, correlation_id_var  # type: ignore
except Exception:  # pragma: no cover
    request_id_var = correlation_id_var = None  # type: ignore


def _corr_headers(extra: Optional[dict] = None) -> dict:
    rid = None
    cid = None
    try:
        rid = request_id_var.get() if request_id_var else None
        cid = correlation_id_var.get() if correlation_id_var else None
    except Exception:
        pass
    if not rid:
        rid = str(uuid.uuid4())
    if not cid:
        cid = rid
    base = {
        "x-request-id": rid,
        "x-correlation-id": cid,
    }
    if extra:
        base.update(extra)
    return base


async def create_artifact(workspace_id: str, artifact: dict, *, idempotency_key: Optional[str] = None) -> dict:
    headers = _corr_headers({"idempotency-key": idempotency_key} if idempotency_key else None)
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=headers) as client:
        r = await client.post(f"{settings.ARTIFACT_SERVICE_URL}/artifact/{workspace_id}", json=artifact)
        if r.is_error:
            # Return rich error so caller can log status/message
            raise httpx.HTTPStatusError(f"{r.status_code}: {r.text}", request=r.request, response=r)
        return r.json()


async def head_artifact(workspace_id: str, artifact_id: str) -> str | None:
    headers = _corr_headers()
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=headers) as client:
        r = await client.head(f"{settings.ARTIFACT_SERVICE_URL}/artifact/{workspace_id}/{artifact_id}")
        return r.headers.get("ETag")
