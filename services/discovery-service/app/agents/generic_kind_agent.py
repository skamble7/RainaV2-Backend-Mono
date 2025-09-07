#services/discovery-service/app/agents/generic_kind_agent.py
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app.llms.registry import get_provider
from app.clients.artifact_service import get_kind_prompt_and_schema


def _canon(k: Optional[str]) -> Optional[str]:
    if not k or not isinstance(k, str):
        return None
    k = k.strip()
    return k or None


def _default_name_for(kind: str) -> str:
    tail = (kind or "").split(".")[-1]
    pretty = tail.replace("_", " ").title()
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
    if isinstance(obj, dict):
        return {k: _strip_dollar_schema(v) for k, v in obj.items() if k != "$schema"}
    if isinstance(obj, list):
        return [_strip_dollar_schema(v) for v in obj]
    return obj


def _to_tool_parameters(json_schema: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(json_schema, dict):
        return {"type": "object", "properties": {}}
    params = _strip_dollar_schema(json_schema)
    if params.get("type") != "object":
        params = {
            "type": "object",
            "properties": {"value": params},
            "required": ["value"],
            "additionalProperties": False,
        }
    return params


def _try_json_loads(s: str):
    try:
        return json.loads(s)
    except Exception:
        return None


def _extract_tool_arguments(resp: Any):
    if resp is None:
        return None
    if isinstance(resp, dict):
        tcs = resp.get("tool_calls")
        if isinstance(tcs, list) and tcs:
            func = (tcs[0] or {}).get("function") or {}
            args = func.get("arguments")
            if isinstance(args, str):
                return _try_json_loads(args) or {}
            if isinstance(args, dict):
                return args
        func = resp.get("function")
        if isinstance(func, dict):
            args = func.get("arguments")
            if isinstance(args, str):
                return _try_json_loads(args) or {}
            if isinstance(args, dict):
                return args
        args = resp.get("arguments")
        if isinstance(args, str):
            return _try_json_loads(args) or {}
        if isinstance(args, dict):
            return args
        content = resp.get("content")
        if isinstance(content, str):
            loaded = _try_json_loads(content)
            if isinstance(loaded, dict):
                return loaded
    if isinstance(resp, str):
        loaded = _try_json_loads(resp)
        if isinstance(loaded, dict):
            return loaded
    return None


class GenericKindAgent:
    """
    Generic "kind-driven" agent that returns upsert patches for /artifacts.
    """
    id = "generic.kind.v1"
    supports = {"paradigms": ["service-based", "event-driven"], "styles": ["microservices"]}
    version = "1.2.0"

    async def run(self, ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        kind = _canon(params.get("kind") or (params.get("produces_kinds") or [None])[0])
        if not kind:
            raise ValueError("GenericKindAgent requires 'kind' in params (and none could be inferred)")

        io = await get_kind_prompt_and_schema(kind)
        system_prompt = io.get("system") or (
            "You are RAINA: return exactly ONE JSON object that conforms to the provided schema. No prose."
        )
        json_schema = io.get("json_schema") or {}

        provider = get_provider(params.get("model_id"))

        user_payload = {
            "inputs": {"avc": ctx.get("avc", {}), "fss": ctx.get("fss", {}), "pss": ctx.get("pss", {})},
            "params": {k: v for k, v in (params or {}).items() if k not in ("internal",)},
            "schema": json_schema,
        }
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, separators=(",", ":"))},
        ]

        data_obj: Dict[str, Any] = {}

        if hasattr(provider, "chat_tools"):
            tool_parameters = _to_tool_parameters(json_schema)
            tools = [{
                "type": "function",
                "function": {
                    "name": "emit_artifact_data",
                    "description": "Return the artifact 'data' object strictly matching the provided schema.",
                    "parameters": tool_parameters,
                },
            }]
            tool_choice = {"type": "function", "function": {"name": "emit_artifact_data"}}
            resp = await provider.chat_tools(messages, tools=tools, tool_choice=tool_choice)
            args = _extract_tool_arguments(resp)
            if isinstance(args, dict):
                data_obj = args
            else:
                if isinstance(resp, dict) and isinstance(resp.get("content"), str):
                    maybe = _try_json_loads(resp["content"])
                    if isinstance(maybe, dict):
                        data_obj = maybe

        if not data_obj:
            if hasattr(provider, "chat_json"):
                content = await provider.chat_json(messages)
            else:
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

        name = params.get("name") or _default_name_for(kind)
        item = {"kind": kind, "name": name, "data": data_obj}
        patches = [{"op": "upsert", "path": "/artifacts", "value": [item]}]
        return {"patches": patches, "telemetry": [{"agent": self.id, "kind": kind}]}
