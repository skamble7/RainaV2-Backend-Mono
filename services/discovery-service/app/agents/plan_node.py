# app/pipeline/plan_node.py

from app.llms.registry import get_provider
from app.models.state import DiscoveryState
from pathlib import Path
import json, logging
logger = logging.getLogger(__name__)

PLAN_PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "plan.txt"

def _norm_step(s: dict) -> dict:
    cap = (s.get("capability") or s.get("capability_id") or "").strip()
    return {
        "id": s.get("id") or cap or "step",
        "capability": cap,
        "params": s.get("params") or {}
    }

async def plan_node(state: DiscoveryState) -> DiscoveryState:
    playbook = state.get("context", {}).get("playbook") or {}
    baseline_steps = [ _norm_step(s) for s in (playbook.get("steps") or []) ]

    # If the playbook truly has no steps, keep an empty plan (or raise)
    if not baseline_steps:
        state["plan"] = {"steps": []}
        state.setdefault("logs", []).append("Plan baseline empty: playbook has no steps")
        return state

    # Start with baseline (pack‑agnostic: exactly what's in the playbook)
    plan = {"steps": baseline_steps}
    state.setdefault("logs", []).append(f"Plan baseline from playbook: {len(baseline_steps)} steps")

    # Optional LLM enrichment — reorder/augment params, but never drop baseline steps
    try:
        # opt‑out switch if you want to skip planning via options
        if state.get("options", {}).get("respect_playbook_strict"):
            state["plan"] = plan
            state["logs"].append("Planner skipped (respect_playbook_strict=true)")
            return state

        provider = get_provider(state.get("model_id"))
        messages = [
            {"role": "system", "content": PLAN_PROMPT.read_text()},
            {"role": "user", "content": json.dumps({"inputs": state["inputs"], "playbook": playbook})}
        ]
        content = await provider.chat_json(messages)
        proposed = json.loads(content) if isinstance(content, str) else content
        proposed_steps = [ _norm_step(s) for s in (proposed.get("steps") or []) ]

        # Merge by id: keep all baseline; overlay params if proposed supplies
        by_id = {s["id"]: s for s in baseline_steps}
        for ps in proposed_steps:
            sid = ps["id"]
            if sid in by_id:
                by_id[sid]["params"] = {**by_id[sid].get("params", {}), **(ps.get("params") or {})}

        # Reorder to proposed order where IDs match; append any baseline not mentioned
        ordered, seen = [], set()
        for ps in proposed_steps:
            if ps["id"] in by_id and ps["id"] not in seen:
                ordered.append(by_id[ps["id"]]); seen.add(ps["id"])
        for b in baseline_steps:
            if b["id"] not in seen:
                ordered.append(b)

        plan["steps"] = ordered
        state["logs"].append("Plan enriched by LLM (no drops)")
    except Exception as e:
        logger.exception("plan_node_enrich_error")
        state.setdefault("errors", []).append(f"plan_node_enrich_error: {e}")

    state["plan"] = plan
    state.setdefault("logs", []).append(f"Final plan steps={len(plan['steps'])}")
    return state
