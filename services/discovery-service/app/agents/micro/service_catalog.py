# app/agents/micro/service_catalog.py
from __future__ import annotations

from pathlib import Path
import json
from typing import Dict, Any, List

from app.agents.spi import RainaAgent, AgentResult, ContextEnvelope
from app.llms.registry import get_provider

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "service_catalog.txt"


class ServiceCatalogAgent:
    id = "catalog.services.v1"
    provides = [{"kind": "cam.capability_model"}]
    # Phase 1: keep requires empty; in Phase 2 we can depend on cam.context_map, etc.
    requires: List[Dict[str, str]] = []
    supports = {"paradigms": ["service-based"], "styles": ["microservices"]}
    version = "1.0.0"

    async def run(self, ctx: ContextEnvelope, params: Dict[str, Any]) -> AgentResult:
        """
        Wraps the existing prompt to generate a service catalog.
        Phase 1 emits upsert-style patches. Each item is normalized to include:
          - kind: cam.capability_model
          - name: "Service Catalog" (if missing)
        """
        provider = get_provider(params.get("model_id"))

        # Build messages for the LLM (system prompt + compact JSON user payload)
        msgs = [
            {"role": "system", "content": PROMPT.read_text()},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "inputs": {
                            "avc": ctx.get("avc", {}),
                            "fss": ctx.get("fss", {}),
                            "pss": ctx.get("pss", {}),
                        },
                        "params": params,
                    },
                    separators=(",", ":"),
                ),
            },
        ]

        # Expecting strict JSON from the provider (your chat_json enforces this)
        content = await provider.chat_json(msgs)

        # Parse into a list of dicts
        parsed = json.loads(content)
        items: List[Dict[str, Any]] = parsed if isinstance(parsed, list) else [parsed]

        normalized: List[Dict[str, Any]] = []
        for it in items:
            if not isinstance(it, dict):
                # Skip non-dict outputs defensively
                continue

            # Ensure CAM kind is explicit (helps adapters & routing)
            it.setdefault("kind", "cam.capability_model")

            # Provide a friendly default name if none is set
            it.setdefault("name", "Service Catalog")

            # Light guardrails (won't raise; just ensure shapes are present)
            it.setdefault("data", {})
            if not isinstance(it["data"], dict):
                # If model returned a non-object for data, coerce to an object
                it["data"] = {"value": it["data"]}

            normalized.append(it)

        # Translate into Phase‑1 patches (backward‑compatible with your pipeline)
        patches = [{"op": "upsert", "path": "/artifacts", "value": it} for it in normalized]

        return {
            "patches": patches,
            "telemetry": [{"agent": self.id}],
        }
