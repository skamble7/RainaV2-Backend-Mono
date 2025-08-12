import httpx
from app.config import settings

class PackResolver:
    def __init__(self, pack_key: str, pack_version: str):
        self.pack_key = pack_key.strip()
        self.pack_version = pack_version.strip()

    async def resolve(self, playbook_id: str) -> dict:
        base = settings.CAPABILITY_REGISTRY_URL.rstrip("/")
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S) as client:
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
