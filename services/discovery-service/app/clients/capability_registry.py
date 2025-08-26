# services/discovery-service/app/clients/capability_registry.py

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


class PackResolver:
    def __init__(self, pack_key: str, pack_version: str):
        self.pack_key = pack_key.strip()
        self.pack_version = pack_version.strip()

    async def resolve(self, playbook_id: str) -> dict:
        base = settings.CAPABILITY_REGISTRY_URL.rstrip("/")
        headers = _corr_headers()

        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=headers) as client:
            p = await client.get(f"{base}/capability/pack/{self.pack_key}/{self.pack_version}")
            p.raise_for_status()
            pack = p.json()

            pb = await client.get(f"{base}/capability/pack/{self.pack_key}/{self.pack_version}/playbooks")
            pb.raise_for_status()
            playbooks = pb.json() or []

            sel = next((x for x in playbooks if x.get("id") == playbook_id), None)
            if not sel:
                raise LookupError(f"playbook {playbook_id} not found in pack {self.pack_key}/{self.pack_version}")
            return {"playbook": sel, "pack": pack}


class CompositeResolver:
    def __init__(self, *resolvers):
        self._resolvers = resolvers

    async def resolve(self, playbook_id: str) -> dict:
        last = None
        for r in self._resolvers:
            try:
                return await r.resolve(playbook_id)
            except LookupError as e:
                last = e
                continue
        raise last or LookupError("No resolver succeeded")
