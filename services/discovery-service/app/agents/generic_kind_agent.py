#services/discovery-service/app/agents/generic_kind_agent.py
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.llms.registry import get_provider
from app.clients.artifact_service import get_kind_prompt_and_schema


def _canon(k: Optional[str]) -> Optional[str]:
    """
    Canonicalize the kind. Legacy aliases have been removed; return the trimmed value.
    """
    if not k or not isinstance(k, str):
        return None
    k = k.strip()
    return k or None


def _default_name_for(kind: str) -> str:
    tail = (kind or "").split(".")[-1]
    pretty = tail.replace("_", " ").title()
    # nicer names for a few common kinds
    overrides = {
        "context": "Context",
        "class": "Class",
        "activity": "Activity",
        "deployment": "Deployment",
        "api": "Api",
        "event": "Event",
        "model": "Model",
        "dictionary": "Dictionary",
        "service": "Service",
        "service_inventory": "Service Inventory",
        "dependency_inventory": "Dependency Inventory",
        "api_inventory": "Api Inventory",
    }
    return overrides.get(tail, pretty) or pretty


def _strip_dollar_schema(obj: Any) -> Any:
    """
    Remove $schema keys recursively so tool-parameter validators that don't
    recognize it won't choke. Keep everything else intact.
    """
    if isinstance(obj, dict):
        return {k: _strip_dollar_schema(v) for k, v in obj.items() if k != "$schema"}
    if isinstance(obj, list):
        return [_strip_dollar_schema(v) for v in obj]
    return obj


def _to_tool_parameters(json_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Coerce a Draft 2020-12 object schema into an OpenAI-style tool/function parameters schema.
    We retain required/enum/const/additionalProperties/etc. and strip only top-level $schema.
    """
    if not isinstance(json_schema, dict):
        return {"type": "object", "properties": {}}

    params = _strip_dollar_schema(json_schema)

    # Tools expect parameters to be an object; if not, wrap minimally.
    if params.get("type") != "object":
        params = {
            "type": "object",
            "properties": {"value": params},
            "required": ["value"],
            "additionalProperties": False,
        }

    # Many of our kinds require a const doc_type; keep it — providers usually pass it through.
    return params


def _try_json_loads(s: str) -> Optional[Any]:
    try:
        return json.loads(s)
    except Exception:
        return None


def _extract_tool_arguments(resp: Any) -> Optional[Dict[str, Any]]:
    """
    Be liberal in what we accept:
      - {"tool_calls":[{"function":{"name":"emit_artifact_data","arguments":"{...}"}}]}
      - {"function":{"name":"emit_artifact_data","arguments":{...}}}
      - {"arguments":{...}}
      - or just a JSON string of the arguments
    """
    if resp is None:
        return None

    # If provider returns the raw message dict (OpenAI-like)
    if isinstance(resp, dict):
        # OpenAI chat.completions style
        tcs = resp.get("tool_calls")
        if isinstance(tcs, list) and tcs:
            func = (tcs[0] or {}).get("function") or {}
            args = func.get("arguments")
            if isinstance(args, str):
                return _try_json_loads(args) or {}
            if isinstance(args, dict):
                return args

        # Some wrappers return {"function": {...}}
        func = resp.get("function")
        if isinstance(func, dict):
            args = func.get("arguments")
            if isinstance(args, str):
                return _try_json_loads(args) or {}
            if isinstance(args, dict):
                return args

        # Some wrappers return {"arguments": {...}}
        args = resp.get("arguments")
        if isinstance(args, str):
            return _try_json_loads(args) or {}
        if isinstance(args, dict):
            return args

        # Or a "content" string with JSON
        content = resp.get("content")
        if isinstance(content, str):
            loaded = _try_json_loads(content)
            if isinstance(loaded, dict):
                return loaded

    # Or plain string
    if isinstance(resp, str):
        loaded = _try_json_loads(resp)
        if isinstance(loaded, dict):
            return loaded

    return None


class GenericKindAgent:
    """
    Generic "kind-driven" agent.

    Requirements:
      - params.kind OR params.produces_kinds[0] must identify the target kind.

    Behavior:
      - fetches the prompt + JSON Schema for the given kind from artifact-service
      - prefers a tool/function-call with the schema as 'parameters' so the model is *forced*
        to output a SINGLE JSON OBJECT that matches the schema (this becomes the artifact 'data')
      - falls back to plain JSON chat if the provider doesn't support tools
      - wraps the result into {kind,name,data} and returns an upsert patch.
    """
    id = "generic.kind.v1"
    supports = {"paradigms": ["service-based", "event-driven"], "styles": ["microservices"]}
    version = "1.2.0"  # bumped for tool-call support

    async def run(self, ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        # Resolve target kind
        pk = params.get("kind") or (params.get("produces_kinds") or [None])[0]
        kind = _canon(pk)
        if not kind:
            raise ValueError("GenericKindAgent requires 'kind' in params (and none could be inferred)")

        # Load prompt + schema from artifact-service (preferred)
        io = await get_kind_prompt_and_schema(kind)
        system_prompt = io.get("system") or (
            "You are RAINA: return exactly ONE JSON object that conforms to the provided schema. No prose."
        )
        json_schema = io.get("json_schema") or {}

        provider = get_provider(params.get("model_id"))

        # Build user content with inputs + params + schema (so the model can follow it)
        user_payload = {
            "inputs": {
                "avc": ctx.get("avc", {}),
                "fss": ctx.get("fss", {}),
                "pss": ctx.get("pss", {}),
            },
            "params": {k: v for k, v in (params or {}).items() if k not in ("internal",)},
            "schema": json_schema,
        }
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, separators=(",", ":"))},
        ]

        data_obj: Dict[str, Any] = {}

        # Prefer tool/function-calling if the provider offers it.
        # Expected signature (duck-typed):
        #   await provider.chat_tools(messages, tools=[...], tool_choice={...}) -> response
        # where response contains tool_calls/function.arguments etc.
        if hasattr(provider, "chat_tools"):
            tool_parameters = _to_tool_parameters(json_schema)
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "emit_artifact_data",
                        "description": "Return the artifact 'data' object strictly matching the provided schema.",
                        "parameters": tool_parameters,
                    },
                }
            ]
            tool_choice = {"type": "function", "function": {"name": "emit_artifact_data"}}

            resp = await provider.chat_tools(messages, tools=tools, tool_choice=tool_choice)
            args = _extract_tool_arguments(resp)
            if isinstance(args, dict):
                data_obj = args
            else:
                # Fallback to plain JSON content if tool extraction failed
                if isinstance(resp, dict) and isinstance(resp.get("content"), str):
                    maybe = _try_json_loads(resp["content"])
                    if isinstance(maybe, dict):
                        data_obj = maybe

        # If we still don't have data, fall back to chat_json
        if not data_obj:
            if hasattr(provider, "chat_json"):
                content = await provider.chat_json(messages)
            else:
                # Last-resort: generic chat that returns a string; try to parse JSON
                content = await provider.chat(messages)  # type: ignore[attr-defined]
            try:
                loaded = json.loads(content)
            except Exception:
                loaded = {}
            if isinstance(loaded, dict):
                data_obj = loaded
            elif isinstance(loaded, list) and loaded and isinstance(loaded[0], dict):
                data_obj = loaded[0]
            else:
                data_obj = {}

        # Compute a stable default name if none provided
        name = params.get("name") or _default_name_for(kind)

        item = {
            "kind": kind,
            "name": name,
            "data": data_obj,
        }

        patches = [{"op": "upsert", "path": "/artifacts", "value": [item]}]
        return {"patches": patches, "telemetry": [{"agent": self.id, "kind": kind}]}
