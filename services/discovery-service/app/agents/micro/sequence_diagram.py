from __future__ import annotations
from pathlib import Path
import json
from app.agents.spi import RainaAgent, AgentResult, ContextEnvelope
from app.llms.registry import get_provider
from app.diagrams.drawio import simple_grid

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "sequence_diagrams.txt"

class SequenceDiagramAgent:
    id = "diagram.sequence.v1"
    provides = [{"kind":"cam.sequence_diagram"}]
    requires = []  # later: services + APIs
    supports = {"paradigms":["service-based"], "styles":["microservices"]}
    version = "1.0.0"

    async def run(self, ctx: ContextEnvelope, params) -> AgentResult:
        provider = get_provider(params.get("model_id"))
        msgs = [
            {"role":"system","content": PROMPT.read_text()},
            {"role":"user","content": json.dumps({"inputs":{"avc":ctx["avc"],"fss":ctx["fss"],"pss":ctx["pss"]},
                                                  "params": params}, separators=(",",":"))}
        ]
        content = await provider.chat_json(msgs)
        sd = json.loads(content)
        if isinstance(sd, list): sd = sd[0]
        sd.setdefault("kind","cam.sequence_diagram")
        sd.setdefault("name","Key User Journeys")

        # Very simple: participants -> nodes; messages -> edges
        parts = sd.get("data",{}).get("participants",[])
        msgs_ = sd.get("data",{}).get("messages",[])
        nodes=[{"id": f"p{i}", "label": p} for i, p in enumerate(parts)]
        edges=[{"id": f"m{i}", "source": f"p{m.get('from_index',0)}", "target": f"p{m.get('to_index',0)}",
                "label": m.get("label","")} for i, m in enumerate(msgs_)]
        sd.setdefault("data",{}).setdefault("diagram_format","drawio")
        sd["data"]["drawio_xml"] = simple_grid(nodes, edges, sd["name"])

        return {"patches":[{"op":"upsert","path":"/artifacts","value":sd}],
                "telemetry":[{"agent": self.id}]}
