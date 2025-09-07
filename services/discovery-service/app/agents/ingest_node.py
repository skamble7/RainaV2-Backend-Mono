# services/discovery-service/app/agents/ingest_node.py
from __future__ import annotations
from app.models.state import DiscoveryState
from app.config import settings
from app.clients.capability_registry import CompositeResolver, PackResolver
import re

def _opt(d: dict, *names: str) -> str:
    for n in names:
        v = d.get(n)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

async def ingest_node(state: DiscoveryState) -> DiscoveryState:
    opts = state.get("options", {}) if isinstance(state.get("options"), dict) else {}
    pack_key_req = _opt(opts, "pack_key", "packKey")
    pack_ver_req = _opt(opts, "pack_version", "packVersion")

    pack_key = pack_key_req or (settings.PACK_KEY or "").strip()
    pack_version = pack_ver_req or (settings.PACK_VERSION or "").strip()

    state.setdefault("logs", []).append(f"Ingest: options={opts} → pack={pack_key}/{pack_version}")
    state.setdefault("logs", []).append(f"Capability registry = {settings.CAPABILITY_REGISTRY_URL}")

    if re.fullmatch(r"v\d+", pack_version):
        state["logs"].append(
            f"NOTE: pack_version looks like major-only '{pack_version}'. If you expected 'v1.2', check client payload keys/casing."
        )

    resolver = CompositeResolver(PackResolver(pack_key, pack_version))
    resolved = await resolver.resolve(state["playbook_id"])
    playbook, pack = resolved["playbook"], resolved["pack"]

    resolved_ver = (pack.get("version") or "").strip()
    if resolved_ver and resolved_ver != pack_version:
        state["logs"].append(
            f"WARNING: resolved pack={pack.get('key')}/{resolved_ver} != requested {pack_key}/{pack_version}"
        )

    cap_map = {c.get("id"): c for c in (pack.get("capabilities") or [])}
    ctx = state.setdefault("context", {})
    ctx["playbook"] = playbook
    ctx["capability_map"] = cap_map
    ctx["pack_key"] = pack_key
    ctx["pack_version"] = pack_version

    state["logs"].append(f"Playbook loaded from pack {pack_key}/{pack_version}: {playbook.get('id')}")
    return state
