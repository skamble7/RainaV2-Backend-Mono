# app/agents/generic.py
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.llms.registry import get_provider
from app.clients.artifact_service import get_kind_prompt

# legacy → canonical aliases (keep in sync with runner/persist)
_ALIAS = {
    "cam.context_map": "cam.diagram.context",
    "cam.erd": "cam.diagram.class",
    "cam.sequence_diagram": "cam.diagram.sequence",
    "cam.component_diagram": "cam.diagram.component",
    "cam.deployment_topology": "cam.diagram.deployment",
    "cam.workflow": "cam.workflow.process",
    "cam.security_policies": "cam.security.policy",
    "cam.service_contract": "cam.contract.api",
    "cam.events": "cam.contract.event",
    "cam.adr_index": "cam.gov.adr.index",
}

def _canon(k: Optional[str]) -> Optional[str]:
    if not k or not isinstance(k, str):
        return None
    k = k.strip()
    return _ALIAS.get(k, k) if k else None


class GenericKindAgent:
    """
    Generic "kind-driven" agent.
    Requirements:
      - params.kind OR params.produces_kinds[0] must identify the target kind.
    Behavior:
      - fetches the discovery prompt for the given kind from artifact-service
      - calls the LLM and returns discovery patches (upsert /artifacts)
      - does *not* enforce a specific JSON shape beyond {kind,name,data}
    """
    id = "generic.kind.v1"
    supports = {"paradigms": ["service-based", "event-driven"], "styles": ["microservices"]}
    version = "1.0.0"

    async def run(self, ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        # Resolve target kind
        pk = params.get("kind") or (params.get("produces_kinds") or [None])[0]
        kind = _canon(pk)
        if not kind:
            raise ValueError("GenericKindAgent requires 'kind' in params (and none could be inferred)")

        # Load prompt from artifact-service (with a safe fallback)
        prompt = await get_kind_prompt(kind)
        if not prompt:
            # ultra-compact meta-prompt fallback
            prompt = (
                "You are RAINA. Produce JSON for the requested artifact kind.\n"
                "Reply with a single JSON object or array. No prose.\n"
                "Infer names & summaries from inputs.\n"
                f"Target kind: {kind}\n"
                "JSON contract: objects must include at least {\"kind\":\"...\",\"name\":\"...\",\"data\":{...}}\n"
            )

        provider = get_provider(params.get("model_id"))
        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "inputs": {
                            "avc": ctx.get("avc", {}),
                            "fss": ctx.get("fss", {}),
                            "pss": ctx.get("pss", {}),
                        },
                        "params": {k: v for k, v in params.items() if k not in ("internal",)},
                    },
                    separators=(",", ":"),
                ),
            },
        ]

        content = await provider.chat_json(messages)
        try:
            items = json.loads(content)
        except Exception:
            # If model returned plain object-ish text, try to coerce; else bubble up
            raise

        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            items = []

        # Attach step id + force kind on each item unless already present
        out: List[dict] = []
        step_id = params.get("_step_id") or params.get("step_id")
        for it in items:
            if not isinstance(it, dict):
                continue
            it.setdefault("kind", kind)
            if step_id:
                it["_step_id"] = step_id
            out.append(it)

        patches = [{"op": "upsert", "path": "/artifacts", "value": out}]
        return {"patches": patches, "telemetry": [{"agent": self.id, "kind": kind}]}
