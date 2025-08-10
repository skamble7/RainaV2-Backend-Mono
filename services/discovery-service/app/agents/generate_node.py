from app.llms.registry import get_provider
from pathlib import Path
import json, logging
from app.models.state import DiscoveryState

logger = logging.getLogger(__name__)
SERV_PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "service_discovery.txt"
SEQ_PROMPT  = Path(__file__).resolve().parents[1] / "prompts" / "sequence_diagrams.txt"

async def generate_node(state: DiscoveryState) -> DiscoveryState:
    provider = get_provider(state.get("model_id"))
    artifacts: list[dict] = state.setdefault("artifacts", [])
    plan_steps = state.get("plan", {}).get("steps", []) or [{"id":"fallback","capability":"discover.services"}]

    for step in plan_steps:
        cap = (step.get("capability") or "").lower()
        prompt_path = SERV_PROMPT if "service" in cap else SEQ_PROMPT
        messages = [
            {"role": "system", "content": prompt_path.read_text()},
            {"role": "user", "content": json.dumps({"inputs": state["inputs"], "step": step})}
        ]
        try:
            content = await provider.chat_json(messages)  # <-- force JSON
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                artifacts.append(parsed)
            elif isinstance(parsed, list):
                artifacts.extend(parsed)
            else:
                artifacts.append({"schema_version":"CAM.v1","kind":"note","data":{"text": str(parsed)}})
        except Exception as e:
            logger.exception("generate_node_parse_error")
            state.setdefault("errors", []).append(f"generate_node_parse_error: {e}")
            # Last resort: save raw text for inspection
            content_fallback = await provider.chat(messages)
            artifacts.append({"schema_version":"CAM.v1","kind":"note","data":{"text": content_fallback}})
    state.setdefault("logs", []).append(f"Generated {len(artifacts)} artifacts")
    return state
