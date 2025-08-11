# app/agents/micro/api_contracts.py
from __future__ import annotations
from pathlib import Path
import json
from typing import Dict, Any
from app.agents.spi import RainaAgent, AgentResult, ContextEnvelope
from app.llms.registry import get_provider

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "api_contracts.txt"

class ApiContractsAgent:
    id = "contracts.api.v1"
    provides = [{"kind": "cam.document"}]  # OpenAPI/grpc sketches
    requires = []  # later: require cam.capability_model or service list
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
