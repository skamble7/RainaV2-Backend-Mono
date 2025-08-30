# app/agents/pipeline/agent_runner.py
# Executes planned steps and emits per-step events.
# Resolves agents via capability_id using app.agents.registry.agent_for_capability.

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.state import DiscoveryState
from app.config import settings
from app.infra.rabbit import publish_event_v1

# If True, a missing/unregistered capability agent marks the step as failed
# but the runner continues to subsequent steps (best-effort discovery).
SOFT_FAIL_ON_RESOLVE_ERROR = True


def _ctx(state: DiscoveryState) -> dict:
    return state.setdefault("context", {})


def _cap_map(state: DiscoveryState) -> dict:
    return _ctx(state).get("capability_map") or {}


def _cap_name(cap: dict) -> str:
    return (cap.get("name") or cap.get("id") or cap.get("capability_id") or "step")


def _cap_kinds(cap: dict) -> List[str]:
    kinds = cap.get("produces_kinds") or []
    return [k for k in kinds if isinstance(k, str)]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _publish(event: str, payload: dict, headers: Optional[dict] = None) -> None:
    publish_event_v1(
        org=settings.EVENTS_ORG,
        event=event,
        payload=payload,
        headers=headers or {},
    )


def _publish_step(status: str, payload: dict, headers: Optional[dict] = None) -> None:
    """
    Compatibility publishing:
      - flat:  raina.discovery.step.v1           (payload.status carries started/completed/failed)
      - dotted: raina.discovery.step.started.v1  (or completed/failed)
    Many consumers bind to raina.discovery.*.v1, which misses dotted variants with extra tokens.
    """
    # Ensure status is present in payload for the flat event
    payload = dict(payload)
    payload["status"] = status
    _publish("step", payload, headers)
    _publish(f"step.{status}", payload, headers)


def _push_step_event(state: DiscoveryState, ev: dict) -> None:
    seq: List[dict] = _ctx(state).setdefault("step_events", [])
    seq.append(ev)


def _resolve_agent_for_capability(capability_id: str):
    from app.agents.registry import agent_for_capability  # local import to avoid cycles
    agent = agent_for_capability(capability_id)
    if not agent:
        raise LookupError(f"Agent not registered for capability '{capability_id}'")
    return agent


# ---- legacy → canonical mapping ----------------------------------------
_ALIAS_TO_CANON = {
    # diagrams
    "cam.context_map": "cam.diagram.context",
    "cam.erd": "cam.diagram.class",
    "cam.sequence_diagram": "cam.diagram.sequence",
    "cam.component_diagram": "cam.diagram.component",
    "cam.deployment_topology": "cam.diagram.deployment",
    # workflows / security / contracts
    "cam.workflow": "cam.workflow.process",
    "cam.security_policies": "cam.security.policy",
    "cam.service_contract": "cam.contract.api",
    "cam.events": "cam.contract.event",
    # misc historical
    "cam.adr_index": "cam.gov.adr.index",
}

def _canon_kind(k: Optional[str]) -> Optional[str]:
    if not k or not isinstance(k, str):
        return None
    k = k.strip()
    if not k:
        return None
    return _ALIAS_TO_CANON.get(k, k)


# ---- core runner --------------------------------------------------------
async def _run_single_step(state: DiscoveryState, step: dict) -> None:
    run_id = _ctx(state).get("run_id")
    workspace_id = state.get("workspace_id")
    playbook_id = state.get("playbook_id")

    cap_id: str = (step.get("capability") or step.get("capability_id") or "").strip()
    step_id: str = (step.get("id") or cap_id or "step").strip()
    params: Dict[str, Any] = dict(step.get("params") or {})

    cap_doc = _cap_map(state).get(cap_id) or {}
    produces_kinds = _cap_kinds(cap_doc)

    # NEW: enrich params so agents can infer the desired kind
    params.setdefault("produces_kinds", produces_kinds)
    if "kind" not in params and produces_kinds:
        params["kind"] = produces_kinds[0]
    if "kind" in params:
        params["kind"] = _canon_kind(params["kind"]) or params["kind"]

    # Also stash per-step meta for persist_node to consult if needed
    _ctx(state).setdefault("step_cap_meta", {})[step_id] = {"produces_kinds": produces_kinds}

    started_at = _utc_now_iso()
    started_payload = {
        "run_id": str(run_id),
        "workspace_id": str(workspace_id),
        "playbook_id": playbook_id,
        "step": {"id": step_id, "capability_id": cap_id, "name": _cap_name(cap_doc)},
        "params": params,
        "started_at": started_at,
        "produces_kinds": produces_kinds,
        "status": "started",
    }
    _publish_step("started", started_payload)
    _push_step_event(state, started_payload)

    t0 = time.perf_counter()

    # Resolve the agent via capability_id
    try:
        agent = _resolve_agent_for_capability(cap_id)
    except Exception as e:
        t1 = time.perf_counter()
        fail = {
            "run_id": str(run_id),
            "workspace_id": str(workspace_id),
            "playbook_id": playbook_id,
            "step": {"id": step_id, "capability_id": cap_id, "name": _cap_name(cap_doc)},
            "params": params,
            "started_at": started_at,
            "ended_at": _utc_now_iso(),
            "duration_s": round(t1 - t0, 3),
            "produces_kinds": produces_kinds,
            "status": "failed",
            "error": f"agent_resolve_error: {e}",
        }
        _publish_step("failed", fail)
        _push_step_event(state, fail)
        state.setdefault("logs", []).append(f"Step {step_id} failed to resolve agent: {e}")
        if SOFT_FAIL_ON_RESOLVE_ERROR:
            return
        raise

    # Run the agent
    try:
        ctx_env = {
            "avc": (state.get("inputs") or {}).get("avc") or {},
            "fss": (state.get("inputs") or {}).get("fss") or {},
            "pss": (state.get("inputs") or {}).get("pss") or {},
            "artifacts": _ctx(state).get("artifacts_snapshot") or {},
        }

        result = await agent.run(ctx_env, params)

        # Merge results (patches → state["artifacts"])
        if result:
            patches = result.get("patches") or []
            if patches:
                state.setdefault("artifacts", [])
                for p in patches:
                    if p.get("op") == "upsert" and p.get("path") == "/artifacts":
                        val = p.get("value")
                        if isinstance(val, dict):
                            state["artifacts"].append(val)
                        elif isinstance(val, list):
                            state["artifacts"].extend(val)

            if result.get("telemetry"):
                _ctx(state).setdefault("telemetry", []).extend(result["telemetry"])
            if result.get("adrs"):
                state.setdefault("adrs", []).extend(result["adrs"])
            if result.get("tasks"):
                _ctx(state).setdefault("tasks", []).extend(result["tasks"])

        t1 = time.perf_counter()
        done = {
            "run_id": str(run_id),
            "workspace_id": str(workspace_id),
            "playbook_id": playbook_id,
            "step": {"id": step_id, "capability_id": cap_id, "name": _cap_name(cap_doc)},
            "params": params,
            "started_at": started_at,
            "ended_at": _utc_now_iso(),
            "duration_s": round(t1 - t0, 3),
            "produces_kinds": produces_kinds,
            "status": "completed",
        }
        _publish_step("completed", done)
        _push_step_event(state, done)

    except Exception as e:
        t1 = time.perf_counter()
        failed_payload = {
            "run_id": str(run_id),
            "workspace_id": str(workspace_id),
            "playbook_id": playbook_id,
            "step": {"id": step_id, "capability_id": cap_id, "name": _cap_name(cap_doc)},
            "params": params,
            "started_at": started_at,
            "ended_at": _utc_now_iso(),
            "duration_s": round(t1 - t0, 3),
            "produces_kinds": produces_kinds,
            "status": "failed",
            "error": str(e),
        }
        _publish_step("failed", failed_payload)
        _push_step_event(state, failed_payload)
        state.setdefault("errors", []).append(f"Step {step_id} failed: {e}")
        raise


async def run_agents(state: DiscoveryState) -> None:
    plan = state.get("plan") or {}
    steps: List[dict] = plan.get("steps") or []
    if not steps:
        return
    for step in steps:
        await _run_single_step(state, step)
