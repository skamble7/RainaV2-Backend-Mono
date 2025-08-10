import httpx
from app.config import settings

async def fetch_playbook(playbook_id: str) -> dict:
    base = settings.CAPABILITY_REGISTRY_URL
    timeout = settings.REQUEST_TIMEOUT_S

    async with httpx.AsyncClient(timeout=timeout) as client:
        # 1) Try standalone endpoint if the registry ever exposes it
        r = await client.get(f"{base}/playbook/{playbook_id}")
        if r.status_code == 200:
            return r.json()
        if r.status_code not in (404, 405):
            r.raise_for_status()  # other errors should surface

        # 2) Fallback: fetch pack and locate the playbook by id
        p = await client.get(f"{base}/capability/pack/{settings.PACK_KEY}/{settings.PACK_VERSION}")
        p.raise_for_status()
        pack = p.json()
        for pb in pack.get("playbooks", []):
            if pb.get("id") == playbook_id:
                # Normalize to the shape the planner/generator expects
                return {
                    "id": pb.get("id"),
                    "name": pb.get("name"),
                    "description": pb.get("description"),
                    "steps": pb.get("steps", [])
                }
        raise httpx.HTTPStatusError(
            f"Playbook '{playbook_id}' not found in pack {settings.PACK_KEY}/{settings.PACK_VERSION}",
            request=p.request, response=p
        )
