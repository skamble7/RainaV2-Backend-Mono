from __future__ import annotations
from pathlib import Path
import json
from app.agents.spi import RainaAgent, AgentResult, ContextEnvelope
from app.llms.registry import get_provider
from app.diagrams.drawio import simple_grid

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "deployment_topology.txt"

class DeploymentTopologyAgent:
    id = "topology.deploy.v1"
    provides = [{"kind":"cam.deployment_topology"}]
    requires = []
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
        topo = json.loads(content)
        if isinstance(topo, list): topo = topo[0]
        topo.setdefault("kind","cam.deployment_topology")
        topo.setdefault("name","K8s Topology")

        nodes=[]
        edges=[]
        # Expect data: {clusters:[{name,ns,services:[]}], gateways:[...], meshes:[...]}
        clusters = topo.get("data",{}).get("clusters",[])
        i=0
        for c in clusters:
            nodes.append({"id": f"cl_{i}", "label": f'Cluster: {c.get("name","")}'})
            for j,s in enumerate(c.get("services",[])):
                nodes.append({"id": f"s_{i}_{j}", "label": s.get("name","svc")})
                edges.append({"id": f"es_{i}_{j}", "source": f"cl_{i}", "target": f"s_{i}_{j}", "label": "hosts"})
            i+=1
        topo.setdefault("data",{}).setdefault("diagram_format","drawio")
        topo["data"]["drawio_xml"] = simple_grid(nodes, edges, topo["name"])

        return {"patches":[{"op":"upsert","path":"/artifacts","value":topo}],
                "telemetry":[{"agent": self.id}]}
