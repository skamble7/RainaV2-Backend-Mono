# app/pipeline/agent_runner.py
from __future__ import annotations
from typing import Any, Dict, List
from app.agents.registry import agent_for_capability

async def run_agents(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Phase 1 runner:
    - Iterates plan steps
    - Resolves agent by capability_id
    - Calls agent.run(ctx, params)
    - Collects patches; for backward-compat, converts them into 'artifacts' list
    """
    plan_steps: List[Dict[str, Any]] = state.get("plan", {}).get("steps", []) or []
    artifacts: List[Dict[str, Any]] = state.setdefault("artifacts", [])
    telemetry_all: List[Dict[str, Any]] = []

    ctx = {
        "avc": state["inputs"].get("avc", {}),
        "fss": state["inputs"].get("fss", {}),
        "pss": state["inputs"].get("pss", {}),
        "artifacts": state.get("artifact_graph", {})  # future snapshot
    }

    for step in plan_steps:
        cap_id = (step.get("capability") or step.get("capability_id") or "").strip()
        step_id = step.get("id") or cap_id or "step"
        agent = agent_for_capability(cap_id)
        if not agent:
            state.setdefault("logs", []).append(f"[runner] No agent for {cap_id}; skipped")
            continue

        params = {**(step.get("params") or {}), "model_id": state.get("model_id")}
        res = await agent.run(ctx, params)
        patches = res.get("patches", [])

        # Backward compatibility: translate upsert patches to raw artifacts
        for p in patches:
            if p.get("op") == "upsert" and p.get("path") == "/artifacts":
                val = p.get("value")
                if isinstance(val, dict):
                    val.setdefault("_step_id", step_id)
                    val.setdefault("_agent_id", agent.id)
                    artifacts.append(val)
                elif isinstance(val, list):
                    for it in val:
                        if isinstance(it, dict):
                            it.setdefault("_step_id", step_id)
                            it.setdefault("_agent_id", agent.id)
                            artifacts.append(it)

        if res.get("telemetry"):
            telemetry_all.extend(res["telemetry"])

    if telemetry_all:
        state.setdefault("telemetry", []).extend(telemetry_all)

    state.setdefault("logs", []).append(f"[runner] Agents produced {len(artifacts)} artifacts")
    return state
