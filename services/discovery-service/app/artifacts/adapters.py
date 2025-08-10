from datetime import datetime
from typing import Dict, Any

class BaseAdapter:
    KIND = "*"
    def normalize(self, cam: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        # generic envelope
        name = cam.get("name") or cam.get("title") or "Document (Generated)"
        data = cam.get("data") if isinstance(cam, dict) and "data" in cam else cam
        return {
            "schema_version": str(cam.get("schema_version") or "1.0"),
            "kind": cam.get("kind") or "cam.document",
            "name": name,
            "title": cam.get("title") or name,
            "version": cam.get("version") or 1,
            "tags": cam.get("tags") or ["generated","discovery"],
            "metadata": {
                **cam.get("metadata", {}),
                "workspace_id": ctx["workspace_id"],
                "source": "discovery-service",
                "playbook_id": ctx["playbook_id"],
                "generated_at": datetime.utcnow().isoformat()+"Z"
            },
            "data": data
        }

class ServiceContractAdapter(BaseAdapter):
    KIND = "cam.service_contract"
    def normalize(self, cam: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        base = super().normalize(cam, ctx)
        base["kind"] = self.KIND
        # ensure a readable name
        if not base.get("name") or base["name"] == "Document (Generated)":
            base["name"] = cam.get("title") or "Service Contract (Generated)"
            base["title"] = base["name"]
        return base

class SequenceDiagramAdapter(BaseAdapter):
    KIND = "cam.sequence_diagram"
    def normalize(self, cam: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        base = super().normalize(cam, ctx)
        base["kind"] = self.KIND
        if not base.get("name") or base["name"] == "Document (Generated)":
            base["name"] = cam.get("title") or "Sequence Diagram (Generated)"
            base["title"] = base["name"]
        return base

ADAPTERS = {
    ServiceContractAdapter.KIND: ServiceContractAdapter(),
    SequenceDiagramAdapter.KIND: SequenceDiagramAdapter(),
    "*": BaseAdapter(),
}

ALLOWED_KINDS = set(ADAPTERS.keys()) - {"*"}
