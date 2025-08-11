# app/agents/micro/service_catalog.py
from __future__ import annotations
from pathlib import Path
import json
from typing import Dict, Any
from app.agents.spi import RainaAgent, AgentResult, ContextEnvelope
from app.llms.registry import get_provider

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "service_catalog.txt"

class ServiceCatalogAgent:
    id = "catalog.services.v1"
    provides = [{"kind": "cam.capability_model"}]
    requires = []  # later: could require cam.context_map
    supports = {"paradigms": ["service-based"], "styles": ["microservices"]}
    version = "1.0.0"

    async def run(self, ctx: ContextEnvelope, params: Dict[str, Any]) -> AgentResult:
        provider = get_provider(params.get("model_id"))
        msgs = [
            {"role": "system", "content": PROMPT.read_text()},
            {"role": "user", "content": json.dumps(
                {"inputs": {"avc": ctx["avc"], "fss": ctx["fss"], "pss": ctx["pss"]},
                 "params": params},
                separators=(",", ":")
            )},
        ]
        content = await provider.chat_json(msgs)
        items = json.loads(content)
        if not isinstance(items, list):
            items = [items]
        patches = [{"op": "upsert", "path": "/artifacts", "value": it} for it in items]
        return {"patches": patches, "telemetry": [{"agent": self.id}]}
