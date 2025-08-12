from __future__ import annotations
from pathlib import Path
import json
from app.agents.spi import RainaAgent, AgentResult, ContextEnvelope
from app.llms.registry import get_provider
from app.diagrams.drawio import simple_grid

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "domain_erd.txt"

class DomainErdAgent:
    id = "domain.erd.v1"
    provides = [{"kind":"cam.erd"}]
    requires = []   # later: could require context map or capability model
    supports = {"paradigms":["service-based"], "styles":["microservices"]}
    version = "1.0.0"

    async def run(self, ctx: ContextEnvelope, params) -> AgentResult:
        provider = get_provider(params.get("model_id"))
        msgs = [
            {"role":"system", "content": PROMPT.read_text()},
            {"role":"user", "content": json.dumps({"inputs":{"avc":ctx["avc"],"fss":ctx["fss"],"pss":ctx["pss"]},
                                                   "params": params}, separators=(",",":"))}
        ]
        content = await provider.chat_json(msgs)
        erd = json.loads(content)
        if isinstance(erd, list): erd = erd[0]
        erd.setdefault("kind","cam.erd")
        erd.setdefault("name","Domain ERD")

        # Draw.io from entities/relations
        ents = erd.get("data",{}).get("entities",[])
        rels = erd.get("data",{}).get("relationships",[])
        nodes = [{"id": f"ent_{i}", "label": e.get("name","Entity")} for i, e in enumerate(ents)]
        name_to_id = {e.get("name",""): f"ent_{i}" for i, e in enumerate(ents)}
        edges=[]
        for i, r in enumerate(rels):
            s = name_to_id.get(r.get("from",""), nodes[0]["id"] if nodes else "ent_0")
            t = name_to_id.get(r.get("to",""), nodes[-1]["id"] if nodes else "ent_0")
            edges.append({"id": f"rel_{i}", "source": s, "target": t, "label": r.get("cardinality","")})
        erd.setdefault("data",{}).setdefault("diagram_format","drawio")
        erd["data"]["drawio_xml"] = simple_grid(nodes, edges, erd["name"])

        return {"patches":[{"op":"upsert","path":"/artifacts","value":erd}],
                "telemetry":[{"agent": self.id}]}
