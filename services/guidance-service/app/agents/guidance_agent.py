from typing import Dict, Any, List, Optional
import json
from app.llms.registry import get_provider
from app.config import settings
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]  # /app/app
SYSTEM = (BASE / "prompts" / "tech_guidance.txt").read_text(encoding="utf-8")

# prompt guardrails
MAX_TOTAL_CHARS = 80000       # allow much richer context
MAX_VALUE_CHARS = 8000
MAX_LIST_ITEMS = 400
MAX_DICT_KEYS = 400


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
            out[k] = _truncate(v.get(k), maxlen)
        return out
    return v


def _compact_artifacts(artifacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    compact_items = []
    total = 0
    for a in artifacts or []:
        obj = {
            "id": a.get("artifact_id") or a.get("_id") or a.get("id"),
            "kind": a.get("kind"),
            "name": a.get("name"),
            "data": _truncate(a.get("data")),
        }
        s = json.dumps(obj, ensure_ascii=False)
        if total + len(s) > MAX_TOTAL_CHARS:
            break
        compact_items.append(obj)
        total += len(s)
    return compact_items


def pack_user_prompt(
    *,
    workspace: Optional[Dict[str, Any]],
    inputs: Optional[Dict[str, Any]],
    artifacts: List[Dict[str, Any]],
    assets: Optional[List[Dict[str, Any]]],
    sections: List[str]
) -> str:
    """
    Build a single rich user message:
      - full workspace meta (name/desc/etc.)
      - inputs_baseline (AVC/FSS/PSS)
      - artifacts (compact/truncated)
      - assets mapping that tells the model where the rendered images live
    """
    compact_items = _compact_artifacts(artifacts)

    payload = {
        "workspace": _truncate(workspace),
        "inputs_baseline": _truncate(inputs),
        "artifacts": compact_items,
        "assets": assets or [],
    }

    header = (
        "You are an expert software architect.\n"
        "Create a LONG, comprehensive, developer-ready **Architecture Guidance** document in Markdown.\n"
        "Use *clear subsections*, tables where helpful, and detailed reasoning. "
        "Cite source artifact IDs inline (e.g., `(source: <id>)`).\n\n"
        "### MUST DO\n"
        f"- Produce these sections in EXACT order: {', '.join(sections)}.\n"
        "- Each section should have multiple paragraphs, lists, and where applicable short tables.\n"
        "- Incorporate workspace inputs (vision/goals/NFRs/constraints/stories/tech_stack) richly.\n"
        "- When an asset has `image_path`, embed it using Markdown: `![<name>](<image_path>)` and give a one-line caption.\n"
        "- Prefer actionable guidance, measurable NFRs, concrete API/Event examples from artifacts.\n"
        "- Cross-reference sections (e.g., ADRs linking to NFRs or APIs).\n\n"
        "### CONTEXT (JSON)\n"
    )
    return header + json.dumps(payload, ensure_ascii=False, indent=2)


async def run_agent(
    artifacts: List[Dict[str, Any]],
    sections: List[str],
    model_id: Optional[str],
    temperature: Optional[float],
    workspace: Optional[Dict[str, Any]] = None,
    inputs: Optional[Dict[str, Any]] = None,
    assets: Optional[List[Dict[str, Any]]] = None,
):
    provider = get_provider(settings.LLM_PROVIDER)
    user = pack_user_prompt(
        workspace=workspace,
        inputs=inputs,
        artifacts=artifacts,
        assets=assets,
        sections=sections,
    )
    return await provider.complete(
        system=SYSTEM,
        user=user,
        model_id=model_id or settings.LLM_MODEL_ID,
        temperature=settings.LLM_TEMP if temperature is None else temperature,
        max_tokens=settings.LLM_MAX_TOKENS,
    )
