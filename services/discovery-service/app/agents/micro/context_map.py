# app/agents/micro/context_map.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List
import hashlib
import json

from app.agents.spi import RainaAgent, AgentResult, ContextEnvelope
from app.llms.registry import get_provider

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "context_map.txt"


def _sha256_text(text: str) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    return h.hexdigest()


class ContextMapAgent:
    id = "decomposer.context_map.v1"
    provides = [{"kind": "cam.context_map"}]
    requires: List[Dict[str, Any]] = []  # future: require AVC/FSS/PSS or domain notes
    supports = {"paradigms": ["service-based"], "styles": ["microservices"]}
    version = "1.0.0"

    async def run(self, ctx: ContextEnvelope, params: Dict[str, Any]) -> AgentResult:
        """
        Phase-1 agent wrapper:
        - Calls the context_map prompt
        - Ensures each emitted item has kind=cam.context_map
        - Adds a default name if missing
        - Emits upsert-style patches for backward compatibility
        - Telemetry includes a prompt hash
        """
        provider = get_provider(params.get("model_id"))
        prompt_text = PROMPT.read_text()
        prompt_hash = _sha256_text(prompt_text)

        msgs = [
            {"role": "system", "content": prompt_text},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "inputs": {"avc": ctx.get("avc", {}), "fss": ctx.get("fss", {}), "pss": ctx.get("pss", {})},
                        "params": params,
                    },
                    separators=(",", ":"),
                ),
            },
        ]

        # Try strict JSON; if it fails, wrap raw content as a diagnostic artifact
        try:
            content = await provider.chat_json(msgs)
            parsed = json.loads(content)
        except Exception as e:
            diag = {
                "kind": "cam.context_map",
                "name": "Cards Microservices Context Map (non-JSON fallback)",
                "data": {
                    "note": "Model returned non-JSON; captured raw string for troubleshooting.",
                    "raw": str(getattr(e, "args", [""])[0])[:2000],
                },
            }
            patches = [{"op": "upsert", "path": "/artifacts", "value": diag}]
            return {"patches": patches, "telemetry": [{"agent": self.id, "prompt_hash": prompt_hash, "fallback": True}]}

        items = parsed if isinstance(parsed, list) else [parsed]
        norm: List[Dict[str, Any]] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            # Ensure correct CAM kind and a reasonable default name
            it.setdefault("kind", "cam.context_map")
            it.setdefault("name", "Cards Microservices Context Map")
            norm.append(it)

        patches = [{"op": "upsert", "path": "/artifacts", "value": it} for it in norm]
        return {"patches": patches, "telemetry": [{"agent": self.id, "prompt_hash": prompt_hash}]}
