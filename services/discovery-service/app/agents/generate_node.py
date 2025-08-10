from app.llms.registry import get_provider
from pathlib import Path
import json
from app.models.state import DiscoveryState

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

# Map capability ids to specific prompt files (add/adjust freely)
PROMPTS = {
    # v1 / v1.1 common
    "cap.discover.services":            "service_discovery.txt",
    "cap.generate.sequence":            "sequence_diagrams.txt",

    # v1.1 additions
    "cap.discover.context_map":         "context_map.txt",
    "cap.catalog.services":             "service_catalog.txt",
    "cap.generate.domain_diagrams":     "domain_erd.txt",          # rename if your ERD prompt differs
    "cap.catalog.events":               "event_catalog.txt",
    "cap.contracts.api":                "api_contracts.txt",
    "cap.tests.consumer_contracts":     "consumer_contracts.txt",   # create a simple JSON-only prompt
    "cap.nfr.matrix":                   "nfr_matrix.txt",
    "cap.deploy.topology":              "deployment_topology.txt",
    "cap.runbooks.slo":                 "runbooks_slo.txt",
    "cap.adr.index":                    "adr_index.txt",
}

# Sensible fallbacks (keeps working if a new cap id appears)
FALLBACK_SERVICE = PROMPTS_DIR / "service_discovery.txt"
FALLBACK_SEQ     = PROMPTS_DIR / "sequence_diagrams.txt"

def pick_prompt_path(cap_id: str) -> Path:
    """Resolve the best prompt file for a capability id with graceful fallbacks."""
    cap_id = (cap_id or "").strip()
    fname = PROMPTS.get(cap_id)
    if fname:
        p = PROMPTS_DIR / fname
        if p.exists():
            return p
    # heuristics if unmapped
    low = cap_id.lower()
    if "sequence" in low:
        return FALLBACK_SEQ
    if "service" in low:
        return FALLBACK_SERVICE
    return FALLBACK_SERVICE  # ultimate fallback

async def generate_node(state: DiscoveryState) -> DiscoveryState:
    provider = get_provider(state.get("model_id"))
    artifacts: list[dict] = state.setdefault("artifacts", [])
    plan_steps = state.get("plan", {}).get("steps", []) or [{"id": "svc-1", "capability": "cap.discover.services"}]

    cap_map = state.get("context", {}).get("capability_map", {})
    step_cap_meta = {}

    for step in plan_steps:
        cap_id = (step.get("capability") or step.get("capability_id") or "").strip()
        cap_meta = cap_map.get(cap_id, {}) or {}
        step_id = step.get("id") or cap_id or "step"

        # retain capability metadata for persistence adapters
        step_cap_meta[step_id] = {
            "capability_id": cap_id,
            "produces_kinds": cap_meta.get("produces_kinds") or []
        }

        prompt_path = pick_prompt_path(cap_id)
        messages = [
            {"role": "system", "content": prompt_path.read_text()},
            {"role": "user", "content": json.dumps({"inputs": state["inputs"], "step": step}, separators=(",", ":"))}
        ]

        # Force JSON output (you already wired chat_json in your provider)
        content = await provider.chat_json(messages)
        parsed = json.loads(content)

        items = parsed if isinstance(parsed, list) else [parsed]
        for it in items:
            if isinstance(it, dict):
                it.setdefault("_step_id", step_id)  # helps persist_node pick kind via produces_kinds
            artifacts.append(it)

    state.setdefault("context", {})["step_cap_meta"] = step_cap_meta
    state.setdefault("logs", []).append(f"Generated {len(artifacts)} artifacts")
    return state
