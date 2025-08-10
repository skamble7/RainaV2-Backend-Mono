from app.llms.registry import get_provider
from app.models.state import DiscoveryState
from pathlib import Path
import json, logging
logger = logging.getLogger(__name__)

PLAN_PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "plan.txt"

async def plan_node(state: DiscoveryState) -> DiscoveryState:
    provider = get_provider(state.get("model_id"))
    messages = [
        {"role": "system", "content": PLAN_PROMPT.read_text()},
        {"role": "user", "content": json.dumps({"inputs": state["inputs"], "playbook": state["context"]["playbook"]})}
    ]
    try:
        content = await provider.chat_json(messages)  # <-- force JSON
        plan = json.loads(content)
    except Exception as e:
        logger.exception("plan_node_parse_error")
        state.setdefault("errors", []).append(f"plan_node_parse_error: {e}")
        # Minimal fallback plan to keep the run moving
        plan = {"steps": [{"id":"fallback","capability":"discover.services"}]}
    state["plan"] = plan
    state.setdefault("logs", []).append("Plan created")
    return state
