from __future__ import annotations
from pathlib import Path
import json
from app.agents.spi import RainaAgent, AgentResult, ContextEnvelope
from app.llms.registry import get_provider

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "authz_policies.txt"

class AuthzPoliciesAgent:
    id = "security.authz.v1"
    provides = [{"kind":"cam.security_policies"}]
    requires = []  # later: service catalog + endpoints
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
        sec = json.loads(content)
        if isinstance(sec, list): sec = sec[0]
        sec.setdefault("kind","cam.security_policies")
        sec.setdefault("name","AuthN/AuthZ Policies")
        return {"patches":[{"op":"upsert","path":"/artifacts","value":sec}],
                "telemetry":[{"agent": self.id}]}
