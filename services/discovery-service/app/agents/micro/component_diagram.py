from __future__ import annotations
from pathlib import Path
import json
from app.agents.spi import RainaAgent, AgentResult, ContextEnvelope
from app.llms.registry import get_provider
from app.diagrams.drawio import simple_grid

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "component_diagram.txt"

class ComponentDiagramAgent:
    id = "diagram.component.v1"
    provides = [{"kind":"cam.component_diagram"}]
    requires = []  # later: service catalog
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
        comp = json.loads(content)
        if isinstance(comp, list): comp = comp[0]
        comp.setdefault("kind","cam.component_diagram")
        comp.setdefault("name","Service Components")

        comps = comp.get("data",{}).get("components",[])
        deps  = comp.get("data",{}).get("dependencies",[])
        nodes=[{"id": f"c{i}", "label": c.get("name","Component")} for i,c in enumerate(comps)]
        name_to_id={c.get("name",""): f"c{i}" for i,c in enumerate(comps)}
        edges=[]
        for i, d in enumerate(deps):
            s = name_to_id.get(d.get("from",""), "c0")
            t = name_to_id.get(d.get("to",""), "c0")
            edges.append({"id": f"d{i}", "source": s, "target": t, "label": d.get("kind","")})
        comp.setdefault("data",{}).setdefault("diagram_format","drawio")
        comp["data"]["drawio_xml"] = simple_grid(nodes, edges, comp["name"])

        return {"patches":[{"op":"upsert","path":"/artifacts","value":comp}],
                "telemetry":[{"agent": self.id}]}
