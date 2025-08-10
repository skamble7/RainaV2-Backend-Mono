from pathlib import Path
from app.llms.registry import get_provider
import json, logging
from app.models.state import DiscoveryState

logger = logging.getLogger(__name__)
VAL_PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "validate.txt"

async def validate_node(state: DiscoveryState) -> DiscoveryState:
    if not state.get("artifacts"):
        return state
    provider = get_provider(state.get("model_id"))
    messages = [
        {"role":"system", "content": VAL_PROMPT.read_text()},
        {"role":"user", "content": json.dumps({"inputs": state["inputs"], "artifacts": state["artifacts"]})}
    ]
    try:
        content = await provider.chat_json(messages)  # <-- force JSON
        result = json.loads(content)
    except Exception as e:
        logger.exception("validate_node_parse_error")
        result = {"issues":[{"severity":"info","message":f"Validator non-JSON: {e}"}]}
    state["validations"] = result.get("issues", [])
    state.setdefault("logs", []).append(f"Validation completed with {len(state['validations'])} issues")
    return state
