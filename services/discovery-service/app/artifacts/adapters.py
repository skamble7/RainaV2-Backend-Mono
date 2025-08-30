from __future__ import annotations
from datetime import datetime
from typing import Dict, Any

class BaseAdapter:
    """Accept any CAM-like dict and wrap a stable envelope."""
    KIND = "*"

    def normalize(self, cam: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        cam = cam or {}
        kind = (cam.get("kind") or ctx.get("kind") or "cam.document").strip()

        # name/title fallbacks
        name = cam.get("name") or cam.get("title") or kind.split(".")[-1].replace("_", " ").title()

        # payload
        if "data" in cam and isinstance(cam["data"], (dict, list, str)):
            data = cam["data"]
        else:
            data = {k: v for k, v in cam.items() if k not in {"schema_version","kind","name","title","tags","metadata","version"}}
            if not data:
                data = cam

        meta = {
            **(cam.get("metadata") or {}),
            "workspace_id": ctx.get("workspace_id"),
            "source": "discovery-service",
            "playbook_id": ctx.get("playbook_id"),
            "run_id": ctx.get("run_id"),
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

        return {
            "schema_version": str(cam.get("schema_version") or "1.0"),
            "kind": kind,
            "name": name,
            "title": cam.get("title") or name,
            "version": cam.get("version") or 1,
            "tags": (cam.get("tags") or []) + ["generated","discovery"],
            "metadata": meta,
            "data": data,
        }

# Legacy aliases so old packs still work
class ServiceContractAdapter(BaseAdapter):
    KIND = "cam.service_contract"
    def normalize(self, cam: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        out = super().normalize(cam, ctx)
        out["kind"] = "cam.contract.api"
        return out

class SequenceDiagramAdapter(BaseAdapter):
    KIND = "cam.sequence_diagram"
    def normalize(self, cam: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        out = super().normalize(cam, ctx)
        out["kind"] = "cam.diagram.sequence"
        return out

ADAPTERS = {
    ServiceContractAdapter.KIND: ServiceContractAdapter(),
    SequenceDiagramAdapter.KIND: SequenceDiagramAdapter(),
    "*": BaseAdapter(),
}

def choose_adapter(kind: str) -> BaseAdapter:
    return ADAPTERS.get((kind or "").strip(), ADAPTERS["*"])

def normalize_for_persist(cam: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    return choose_adapter(cam.get("kind") or ctx.get("kind") or "").normalize(cam, ctx)

# No hard gating anymore — forward compatible with new kinds
def is_supported_kind(kind: str) -> bool:
    return isinstance(kind, str) and kind.startswith("cam.")
