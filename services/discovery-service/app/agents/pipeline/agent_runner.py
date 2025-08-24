# app/pipeline/agent_runner.py
from __future__ import annotations
from typing import Any, Dict, List
import asyncio

from app.agents.registry import agent_for_capability

DEFAULT_STEP_TIMEOUT_SEC = 60  # tweak as you like

def _cap_meta(state: Dict[str, Any], step_id: str) -> Dict[str, Any]:
    return (state.get("context", {}).get("step_cap_meta", {}) or {}).get(step_id, {})

async def run_agents(state: Dict[str, Any]) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = state.get("plan", {}).get("steps", []) or []
    artifacts: List[Dict[str, Any]] = state.setdefault("artifacts", [])
    failures: List[Dict[str, Any]] = state.setdefault("agent_failures", [])
    telemetry_all: List[Dict[str, Any]] = state.setdefault("telemetry", [])

    ctx = {
        "avc": state.get("inputs", {}).get("avc", {}),
        "fss": state.get("inputs", {}).get("fss", {}),
        "pss": state.get("inputs", {}).get("pss", {}),
        "artifacts": state.get("artifact_graph", {})  # snapshot if you maintain one
    }

    for step in steps:
        cap_id = (step.get("capability") or step.get("capability_id") or "").strip()
        step_id = step.get("id") or cap_id or "step"
        agent = agent_for_capability(cap_id)
        if not agent:
            state.setdefault("logs", []).append(f"[runner] No agent for {cap_id}; skipped")
            failures.append({"step_id": step_id, "capability": cap_id, "error": "no_agent"})
            continue

        params = {**(step.get("params") or {}), "model_id": state.get("model_id")}
        try:
            # per-step timeout so a single agent can’t hang the whole run
            res = await asyncio.wait_for(agent.run(ctx, params), timeout=DEFAULT_STEP_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            failures.append({"step_id": step_id, "capability": cap_id, "error": "timeout"})
            state.setdefault("logs", []).append(f"[runner] Agent timeout {cap_id} (step {step_id})")
            continue
        except Exception as e:
            failures.append({"step_id": step_id, "capability": cap_id, "error": str(e)})
            state.setdefault("logs", []).append(f"[runner] Agent error {cap_id}: {e}")
            continue

        patches = res.get("patches", []) or []
        produced = 0

        # Pack metadata (for kind fallback)
        meta = _cap_meta(state, step_id)
        produces_kinds = meta.get("produces_kinds") or []

        for p in patches:
            if p.get("op") != "upsert" or p.get("path") != "/artifacts":
                continue
            val = p.get("value")
            items = val if isinstance(val, list) else [val]
            for it in items:
                if not isinstance(it, dict):
                    continue
                # Ensure step/agent trace
                it.setdefault("_step_id", step_id)
                it.setdefault("_agent_id", getattr(agent, "id", ""))

                # Kind fallback from pack’s produces_kinds
                k = (it.get("kind") or "").strip()
                if not k and produces_kinds:
                    it["kind"] = produces_kinds[0]

                # Name/data guardrails (helps adapters)
                it.setdefault("name", step.get("name") or f"{cap_id} ({step_id})")
                it.setdefault("data", {})

                artifacts.append(it)
                produced += 1

        # Telemetry
        tel = res.get("telemetry") or []
        if tel:
            telemetry_all.extend(tel)
        else:
            telemetry_all.append({"agent": getattr(agent, "id", ""), "step_id": step_id, "produced": produced})

        # If nothing was produced, flag it clearly
        if produced == 0:
            msg = f"[runner] No artifacts from step {step_id} ({cap_id})"
            state.setdefault("logs", []).append(msg)
            failures.append({"step_id": step_id, "capability": cap_id, "error": "no_output"})

    state.setdefault("logs", []).append(
        f"[runner] steps={len(steps)} artifacts={len(artifacts)} failures={len(failures)}"
    )
    return state
