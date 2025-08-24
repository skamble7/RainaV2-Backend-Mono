# app/agents/micro/api_contracts.py
from __future__ import annotations
from pathlib import Path
import json
from typing import Dict, Any, List
from app.agents.spi import AgentResult, ContextEnvelope
from app.llms.registry import get_provider

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "api_contracts.txt"


class ApiContractsAgent:
    """
    Phase-1 thin agent that wraps the `api_contracts.txt` prompt and emits
    upsert-style patches. Adds minimal normalization so downstream adapters get
    a consistent CAM shape.
    """
    id = "contracts.api.v1"
    provides = [{"kind": "cam.document"}]  # OpenAPI/gRPC sketches
    requires: List[dict] = []  # later: [{"kind":"cam.capability_model"}]
    supports = {"paradigms": ["service-based"], "styles": ["microservices"]}
    version = "1.0.1"

    async def run(self, ctx: ContextEnvelope, params: Dict[str, Any]) -> AgentResult:
        # Defaults (non-breaking)
        style = (params.get("style") or "rest").lower()
        model_id = params.get("model_id")

        provider = get_provider(model_id)
        msgs = [
            {"role": "system", "content": PROMPT.read_text()},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "inputs": {
                            "avc": ctx.get("avc", {}),
                            "fss": ctx.get("fss", {}),
                            "pss": ctx.get("pss", {}),
                        },
                        "params": {**params, "style": style},
                    },
                    separators=(",", ":"),
                ),
            },
        ]

        content = await provider.chat_json(msgs)
        items = json.loads(content)
        if not isinstance(items, list):
            items = [items]

        normalized: List[dict] = []
        for it in items:
            if not isinstance(it, dict):
                # Skip non-dict junk defensively
                continue
            normalized.append(self._normalize_item(it, style))

        patches = [{"op": "upsert", "path": "/artifacts", "value": it} for it in normalized]
        return {"patches": patches, "telemetry": [{"agent": self.id}]}

    @staticmethod
    def _normalize_item(it: Dict[str, Any], style: str) -> Dict[str, Any]:
        """
        Ensure a consistent CAM document:
          - kind: cam.document
          - name: "API Contracts" (if missing)
          - data.doc_type = "api_contracts"
          - carry through common top-level fields if caller already set them
        """
        it.setdefault("kind", "cam.document")
        it.setdefault("name", "API Contracts")

        # If the model returned top-level fields (e.g., services) instead of wrapping under data,
        # move them under data and set doc_type.
        data = it.get("data")
        if not isinstance(data, dict):
            # Collect non-metadata fields to move under data
            move_keys = []
            for k, v in list(it.items()):
                if k in ("kind", "name", "_step_id", "_agent_id", "version", "created_at", "updated_at", "deleted_at", "provenance"):
                    continue
                # Heuristic: typical fields the prompt may emit at top-level
                if k in ("services", "openapi", "grpc_idl", "doc_type"):
                    move_keys.append(k)

            data_obj: Dict[str, Any] = {"doc_type": "api_contracts"}
            for k in move_keys:
                data_obj[k] = it.pop(k)

            # If nothing was moved but data is still missing, ensure a minimal envelope
            if len(data_obj) == 1:  # only doc_type present
                data_obj["services"] = []

            it["data"] = data_obj
        else:
            data.setdefault("doc_type", "api_contracts")

        # Optional: enforce style hint at data-level if present
        if isinstance(it.get("data"), dict):
            it["data"].setdefault("style", style)

        return it
