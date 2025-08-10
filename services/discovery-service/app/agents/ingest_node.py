from app.models.state import DiscoveryState
from app.config import settings
from app.clients.capability_registry import CompositeResolver, RegistryStandaloneResolver, PackResolver

async def ingest_node(state: DiscoveryState) -> DiscoveryState:
    # resolve pack source: request overrides > env defaults
    opts = state.get("options", {}) if isinstance(state.get("options"), dict) else {}
    pack_key = opts.get("pack_key") or settings.PACK_KEY
    pack_version = opts.get("pack_version") or settings.PACK_VERSION

    resolver = CompositeResolver(
        RegistryStandaloneResolver(),
        PackResolver(pack_key, pack_version)
    )

    resolved = await resolver.resolve(state["playbook_id"])
    # If standalone returned only the playbook, normalize shape
    if "playbook" in resolved and "pack" in resolved:
        playbook = resolved["playbook"]
        pack = resolved["pack"]
    else:
        playbook = resolved
        pack = {}

    # Build capability map for later (for produces_kinds)
    cap_map = {}
    for c in (pack.get("capabilities") or []):
        cap_map[c.get("id")] = c

    ctx = state.setdefault("context", {})
    ctx["playbook"] = playbook
    ctx["capability_map"] = cap_map
    ctx["pack_key"] = pack_key
    ctx["pack_version"] = pack_version

    state.setdefault("logs", []).append(f"Playbook loaded (pack {pack_key}/{pack_version})")
    return state
