import httpx
from typing import List, Dict, Any, Optional
from app.config import settings
import logging

log = logging.getLogger(__name__)

class ArtifactClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or settings.ARTIFACT_SERVICE_URL
        self._client = httpx.AsyncClient(timeout=60)

    async def fetch_cam_artifacts(
        self, workspace_id: str, kinds: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        params = {}
        if kinds:
            params["kinds"] = ",".join(kinds)
        # list artifacts for a workspace
        r = await self._client.get(f"{self.base_url}/artifact/{workspace_id}", params=params)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("items", "data", "results"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        log.warning("Unexpected response shape from artifact list: %s", type(data))
        return []

    async def persist_document(self, workspace_id: str, document: Dict[str, Any]) -> str:
        # Persist as cam.document, with our structured guidance under `data`
        payload = {
            "kind": "cam.document",
            "name": "Technical Architecture & Design Guidance",
            "data": document,   # document already has doc_type="tech_guidance"
        }
        r = await self._client.post(f"{self.base_url}/artifact/{workspace_id}", json=payload)
        r.raise_for_status()
        body = r.json()
        return body.get("id") or body.get("_id") or body.get("artifact_id")

    async def get_artifact(self, workspace_id: str, artifact_id: str) -> Dict[str, Any]:
        r = await self._client.get(f"{self.base_url}/artifact/{workspace_id}/{artifact_id}")
        r.raise_for_status()
        return r.json()
