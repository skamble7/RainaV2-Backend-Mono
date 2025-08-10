from typing import Dict, Any, List
import json
from app.llms.registry import get_provider
from app.config import settings
from pathlib import Path
BASE = Path(__file__).resolve().parents[1]  # /app/app
SYSTEM = (BASE / "prompts" / "tech_guidance.txt").read_text(encoding="utf-8")


SYSTEM = open("app/prompts/tech_guidance.txt", "r", encoding="utf-8").read()

# simple guards to keep prompts within budget
MAX_TOTAL_CHARS = 16000        # total JSON bytes from artifacts
MAX_VALUE_CHARS = 2000         # per-string cap
MAX_LIST_ITEMS = 100           # per-list cap
MAX_DICT_KEYS = 100            # per-dict cap

def _truncate(v, maxlen=MAX_VALUE_CHARS):
    if v is None:
        return None
    if isinstance(v, str):
        return (v[:maxlen] + "…") if len(v) > maxlen else v
    if isinstance(v, list):
        return [_truncate(i, maxlen) for i in v[:MAX_LIST_ITEMS]]
    if isinstance(v, dict):
        out = {}
        for k in list(v.keys())[:MAX_DICT_KEYS]:
            out[k] = _truncate(v[k], maxlen)
        return out
    return v

def pack_user_prompt(artifacts: List[Dict[str, Any]], sections: List[str]) -> str:
    compact_items = []
    total = 0
    for a in artifacts:
        obj = {
            "id": a.get("_id") or a.get("id"),
            "kind": a.get("kind"),
            "name": a.get("name"),
            "data": _truncate(a.get("data")),
        }
        s = json.dumps(obj, ensure_ascii=False)
        if total + len(s) > MAX_TOTAL_CHARS:
            break
        compact_items.append(obj)
        total += len(s)

    header = (
        "Produce the following sections as Markdown using '## <section>' headings, "
        "in this exact order: " + ", ".join(sections) + ". "
        "Each section must be actionable and reference relevant source artifact ids. "
        "Make NFRs measurable.\n\n"
        "=== CAM Artifacts (JSON) ===\n"
    )
    return header + json.dumps(compact_items, ensure_ascii=False, indent=2)

async def run_agent(
    artifacts: List[Dict[str, Any]],
    sections: List[str],
    model_id: str | None,
    temperature: float | None
):
    provider = get_provider(settings.LLM_PROVIDER)
    user = pack_user_prompt(artifacts, sections)
    return await provider.complete(
        system=SYSTEM,
        user=user,
        model_id=model_id or settings.LLM_MODEL_ID,
        temperature=settings.LLM_TEMP if temperature is None else temperature,
        max_tokens=settings.LLM_MAX_TOKENS,
    )
