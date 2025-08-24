# app/agents/micro/context_map.py
from __future__ import annotations
from pathlib import Path
import json
from typing import Dict, Any
from app.agents.spi import RainaAgent, AgentResult, ContextEnvelope
from app.llms.registry import get_provider
from app.diagrams.drawio import simple_grid

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "context_map.txt"

class ContextMapAgent:
    # ← This is the value you reference in the pack
    id = "decomposer.context_map.v1"
    provides = [{"kind": "cam.context_map"}]
    requires = []  # (we'll add dependencies in Phase 2)
    supports = {"paradigms": ["service-based"], "styles": ["microservices"]}
    version = "1.0.0"

    async def run(self, ctx: ContextEnvelope, params: Dict[str, Any]) -> AgentResult:
        provider = get_provider(params.get("model_id"))
        msgs = [
            {"role": "system", "content": PROMPT.read_text()},
            {"role": "user", "content": json.dumps(
                {"inputs": {"avc": ctx["avc"], "fss": ctx["fss"], "pss": ctx["pss"]},
                 "params": params}, separators=(",", ":"))
            }
        ]
        content = await provider.chat_json(msgs)
        item = json.loads(content)
        if isinstance(item, list):
            item = item[0]

        # Ensure kind + name
        item.setdefault("kind", "cam.context_map")
        item.setdefault("name", "Cards Microservices Context Map")

        # Draw.io
        contexts = item.get("data", {}).get("contexts", [])
        rels = item.get("data", {}).get("relationships", [])
        nodes = [{"id": f"ctx_{i}", "label": c.get("name", "Context")} for i, c in enumerate(contexts)]
        name_to_id = {c.get("name", ""): f"ctx_{i}" for i, c in enumerate(contexts)}
        edges = []
        for i, r in enumerate(rels):
            s = name_to_id.get(r.get("from", ""), nodes[0]["id"] if nodes else "ctx_0")
            t = name_to_id.get(r.get("to", ""), nodes[-1]["id"] if nodes else "ctx_0")
            edges.append({"id": f"e{i}", "source": s, "target": t, "label": r.get("style", "")})
        item.setdefault("data", {}).setdefault("diagram_format", "drawio")
        item["data"]["drawio_xml"] = simple_grid(nodes, edges, item["name"])

        return {
            "patches": [{"op": "upsert", "path": "/artifacts", "value": item}],
            "telemetry": [{"agent": self.id}],
        }
