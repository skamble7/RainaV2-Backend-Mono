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
        """
        Legacy/simple list of artifacts for a workspace.
        Prefer fetch_workspace_with_artifacts() when you need workspace metadata and inputs.
        """
        params = {}
        if kinds:
            params["kinds"] = ",".join(kinds)
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

    async def fetch_workspace_with_artifacts(
        self, workspace_id: str, include_deleted: bool = False
    ) -> Dict[str, Any]:
        """
        Fetches the parent bundle that includes:
          - workspace metadata under 'workspace'
          - artifacts under 'artifacts'
          - inputs_baseline (e.g., avc/fss/pss) and more
        Endpoint example:
          GET /artifact/{workspace_id}/parent?include_deleted=false
        """
        url = f"{self.base_url}/artifact/{workspace_id}/parent"
        params = {"include_deleted": str(include_deleted).lower()}
        r = await self._client.get(url, params=params)
        r.raise_for_status()
        body = r.json()
        if not isinstance(body, dict):
            log.warning("Unexpected response shape from parent bundle: %s", type(body))
            return {}
        return body
