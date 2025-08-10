import httpx
from app.config import settings

class RegistryStandaloneResolver:
    async def resolve(self, playbook_id: str) -> dict:
        base = settings.CAPABILITY_REGISTRY_URL
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S) as client:
            r = await client.get(f"{base}/playbook/{playbook_id}")
            if r.status_code == 200:
                return r.json()
            if r.status_code in (404, 405):
                raise LookupError("standalone_not_found")
            r.raise_for_status()
        raise LookupError("standalone_not_found")

class PackResolver:
    def __init__(self, pack_key: str, pack_version: str):
        self.pack_key = pack_key
        self.pack_version = pack_version

    async def resolve(self, playbook_id: str) -> dict:
        base = settings.CAPABILITY_REGISTRY_URL
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S) as client:
            p = await client.get(f"{base}/capability/pack/{self.pack_key}/{self.pack_version}")
            p.raise_for_status()
            pack = p.json()
            # return playbook + capability metadata so downstream can use produces_kinds
            for pb in pack.get("playbooks", []) or []:
                if pb.get("id") == playbook_id:
                    return {"playbook": pb, "pack": pack}
        raise LookupError(f"playbook {playbook_id} not found in pack {self.pack_key}/{self.pack_version}")

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
