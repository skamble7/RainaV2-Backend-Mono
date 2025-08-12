from __future__ import annotations
from pathlib import Path
import json
from app.agents.spi import RainaAgent, AgentResult, ContextEnvelope
from app.llms.registry import get_provider
from app.diagrams.drawio import simple_grid

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "app_workflows.txt"

class AppWorkflowsAgent:
    id = "workflow.app.v1"
    provides = [{"kind":"cam.workflow"}]
    requires = []  # later: events/services
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
        wf = json.loads(content)
        if isinstance(wf, list): wf = wf[0]
        wf.setdefault("kind","cam.workflow")
        wf.setdefault("name","Application Workflows")

        steps = wf.get("data",{}).get("steps",[])
        nodes=[{"id": f"st{i}", "label": s.get("name","Step")} for i, s in enumerate(steps)]
        edges=[]
        for i in range(len(steps)-1):
            edges.append({"id": f"edge{i}", "source": f"st{i}", "target": f"st{i+1}", "label": ""})
        wf.setdefault("data",{}).setdefault("diagram_format","drawio")
        wf["data"]["drawio_xml"] = simple_grid(nodes, edges, wf["name"])

        return {"patches":[{"op":"upsert","path":"/artifacts","value":wf}],
                "telemetry":[{"agent": self.id}]}
