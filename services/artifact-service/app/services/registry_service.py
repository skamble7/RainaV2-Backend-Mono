# services/artifact-service/app/services/registry_service.py
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase

try:
    import fastjsonschema  # type: ignore
except Exception:  # pragma: no cover - optional dep
    fastjsonschema = None  # type: ignore

try:
    from jsonschema import Draft202012Validator  # type: ignore
except Exception:  # pragma: no cover
    Draft202012Validator = None  # type: ignore

from app.dal.kind_registry_dal import (
    ensure_registry_indexes,
    get_registry_meta,
    list_kinds,
    resolve_kind as dal_resolve_kind,
    get_schema_version_entry,
)
from app.models.kind_registry import KindRegistryDoc


# ─────────────────────────────────────────────────────────────
# Small JSON/dict helpers (safe, no eval)
# ─────────────────────────────────────────────────────────────

def _canonical(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))

def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _dot_get(obj: Any, path: str, default: Any = "") -> Any:
    """Very small dotted path reader, supports list indices like items.0.name"""
    cur = obj
    if path == "" or path is None:
        return cur
    for part in path.split("."):
        if isinstance(cur, list):
            try:
                idx = int(part)
            except Exception:
                return default
            if 0 <= idx < len(cur):
                cur = cur[idx]
            else:
                return default
        elif isinstance(cur, dict):
            if part in cur:
                cur = cur[part]
            else:
                return default
        else:
            return default
    return cur

def _dot_set(obj: Dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur: Any = obj
    for i, p in enumerate(parts):
        last = (i == len(parts) - 1)
        if last:
            if isinstance(cur, dict):
                cur[p] = value
            elif isinstance(cur, list):
                idx = int(p)
                while len(cur) <= idx:
                    cur.append(None)
                cur[idx] = value
            else:
                raise ValueError(f"Cannot set into non-container at '{p}'")
        else:
            nxt: Any
            if isinstance(cur, dict):
                if p not in cur or not isinstance(cur[p], (dict, list)):
                    # default to dict
                    cur[p] = {}
                nxt = cur[p]
            elif isinstance(cur, list):
                idx = int(p)
                while len(cur) <= idx:
                    cur.append({})
                nxt = cur[idx]
            else:
                raise ValueError(f"Cannot traverse into non-container at '{p}'")
            cur = nxt

def _dot_delete(obj: Dict[str, Any], path: str) -> None:
    parts = path.split(".")
    cur: Any = obj
    for i, p in enumerate(parts):
        last = (i == len(parts) - 1)
        if not last:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            elif isinstance(cur, list):
                cur = cur[int(p)]
            else:
                return
        else:
            if isinstance(cur, dict) and p in cur:
                del cur[p]
            elif isinstance(cur, list):
                idx = int(p)
                if 0 <= idx < len(cur):
                    cur.pop(idx)


# ─────────────────────────────────────────────────────────────
# Simple declarative adapter DSL
# ─────────────────────────────────────────────────────────────
def _apply_adapter_dsl(data: Dict[str, Any], dsl: Dict[str, Any]) -> Dict[str, Any]:
    """
    Supported keys:
      - move: { "from.path": "to.path", ... }
      - set:  { "path": value, ... }   (always sets, overwriting)
      - defaults: { "path": value, ... } (only if missing/falsy)
      - delete: ["path", "path2"]
    """
    out = json.loads(json.dumps(data))  # cheap deep copy
    for src, dst in (dsl.get("move") or {}).items():
        val = _dot_get(out, src, default=None)
        if val is not None:
            _dot_set(out, dst, val)
            _dot_delete(out, src)
    for p, v in (dsl.get("set") or {}).items():
        _dot_set(out, p, v)
    for p, v in (dsl.get("defaults") or {}).items():
        cur = _dot_get(out, p, default=None)
        if cur in (None, "", [], {}):
            _dot_set(out, p, v)
    for p in (dsl.get("delete") or []):
        _dot_delete(out, p)
    return out


# ─────────────────────────────────────────────────────────────
# JSON Schema validation (fastjsonschema with fallback)
# ─────────────────────────────────────────────────────────────
class _ValidatorCache:
    def __init__(self) -> None:
        self._compiled: Dict[str, Any] = {}

    def key(self, kind_id: str, version: str) -> str:
        return f"{kind_id}@{version}"

    def get(self, key: str) -> Optional[Any]:
        return self._compiled.get(key)

    def set(self, key: str, validator: Any) -> None:
        self._compiled[key] = validator


_validator_cache = _ValidatorCache()


def _compile_validator(kind_id: str, version: str, json_schema: Dict[str, Any]):
    cache_key = _validator_cache.key(kind_id, version)
    cached = _validator_cache.get(cache_key)
    if cached:
        return cached

    if fastjsonschema is not None:
        validator = fastjsonschema.compile(json_schema)  # returns a callable
    elif Draft202012Validator is not None:
        v = Draft202012Validator(json_schema)
        def validator(instance: Any) -> None:
            v.validate(instance)
    else:
        raise RuntimeError("No JSON Schema validator available (install fastjsonschema or jsonschema)")
    _validator_cache.set(cache_key, validator)
    return validator


# ─────────────────────────────────────────────────────────────
# Prompt selection / variant matching
# ─────────────────────────────────────────────────────────────
def _matches_when(selectors: Dict[str, Any], when: Optional[Dict[str, Any]]) -> bool:
    if not when:
        return False
    # all keys in 'when' must match incoming selectors (case-insensitive for strings)
    for k, v in when.items():
        sv = selectors.get(k)
        if isinstance(v, str) and isinstance(sv, str):
            if v.lower() != sv.lower():
                return False
        else:
            if v != sv:
                return False
    return True


# ─────────────────────────────────────────────────────────────
# Identity helpers (NK/summary/category)
# ─────────────────────────────────────────────────────────────
_JINJA_RX = re.compile(r"{{\s*([^}]+)\s*}}")


def _render_template(rule: str, ctx: Dict[str, Any]) -> str:
    """
    Very small mustache-like renderer resolving dotted paths in {{ ... }}.
    """
    def repl(m: re.Match[str]) -> str:
        path = m.group(1)
        val = _dot_get(ctx, path, default="")
        if isinstance(val, (dict, list)):
            try:
                return json.dumps(val, separators=(",", ":"))
            except Exception:
                return ""
        return str(val)
    return _JINJA_RX.sub(repl, rule).strip()


def _compute_natural_key(kind_id: str, name: str, ident_spec: Optional[Dict[str, Any]], data: Dict[str, Any]) -> str:
    if ident_spec and ident_spec.get("natural_key"):
        nk = ident_spec["natural_key"]
        if isinstance(nk, list) and nk:
            parts: List[str] = []
            for p in nk:
                parts.append(str(_dot_get({"data": data, "name": name}, str(p), default="")).strip().lower())
            parts = [p for p in parts if p]
            if parts:
                return f"{kind_id}:{':'.join(parts)}"
        elif isinstance(nk, str) and nk:
            val = str(_dot_get({"data": data, "name": name}, nk, default="")).strip().lower()
            if val:
                return f"{kind_id}:{val}"
    # Fallback: kind + name
    return f"{kind_id}:{name}".lower().strip()


def _compute_summary(name: str, ident_spec: Optional[Dict[str, Any]], data: Dict[str, Any]) -> str:
    rule = (ident_spec or {}).get("summary_rule")
    if isinstance(rule, str) and rule.strip():
        return _render_template(rule, {"data": data, "name": name}) or name
    return name


def _compute_category(kind_id: str, kind_doc: Optional[KindRegistryDoc]) -> str:
    if kind_doc and kind_doc.category:
        return kind_doc.category
    # derive from cam.<category>.<artifact>
    parts = kind_id.split(".")
    return parts[1] if len(parts) >= 3 else parts[0]


# ─────────────────────────────────────────────────────────────
# Main Service
# ─────────────────────────────────────────────────────────────
class KindRegistryService:
    """
    High-level service:
      - cache registry (by ETag),
      - resolve aliases,
      - choose prompt variant,
      - adapt → migrate → validate,
      - compute identity & envelope.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self._etag: Optional[str] = None
        self._kinds: Dict[str, KindRegistryDoc] = {}
        self._aliases: Dict[str, str] = {}

    # ── cache management ──────────────────────────────────────
    async def refresh_cache(self, force: bool = False) -> None:
        await ensure_registry_indexes(self.db)
        meta = await get_registry_meta(self.db)
        if (not force) and self._etag and meta.etag == self._etag:
            return

        # Rebuild maps
        all_docs = await list_kinds(self.db, limit=2000)
        kinds: Dict[str, KindRegistryDoc] = {}
        aliases: Dict[str, str] = {}
        for d in all_docs:
            kd = KindRegistryDoc(**d)
            kinds[kd.id] = kd
            for a in kd.aliases or []:
                aliases[a] = kd.id

        self._kinds = kinds
        self._aliases = aliases
        self._etag = meta.etag

    async def _get_kind_doc(self, kind_or_alias: str) -> Optional[KindRegistryDoc]:
        # Fast path: cache
        await self.refresh_cache()
        kd = self._kinds.get(kind_or_alias)
        if kd:
            return kd
        resolved = self._aliases.get(kind_or_alias)
        if resolved and resolved in self._kinds:
            return self._kinds[resolved]
        # Slow path fallback to DAL (in case of cache skew)
        kd = await dal_resolve_kind(self.db, kind_or_alias)
        if kd:
            # update cache maps minimally
            self._kinds[kd.id] = kd
            for a in kd.aliases or []:
                self._aliases[a] = kd.id
        return kd

    # ── prompt selection ──────────────────────────────────────
    async def select_prompt(
        self,
        kind_or_alias: str,
        *,
        version: Optional[str] = None,
        selectors: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Returns: { "system": str, "user_template": str|None, "io_hints": {...}, "prompt_rev": int, "version": str }
        """
        kd = await self._get_kind_doc(kind_or_alias)
        if not kd:
            return None
        entry = await get_schema_version_entry(self.db, kd.id, version=version)
        if not entry:
            return None

        prompt = entry.get("prompt") or {}
        system = prompt.get("system")
        user_template = prompt.get("user_template")
        io_hints = prompt.get("io_hints")
        prompt_rev = int(prompt.get("prompt_rev") or 1)

        sels = selectors or {}
        # pick first matching variant
        for v in (prompt.get("variants") or []):
            if _matches_when(sels, v.get("when")):
                system = v.get("system") or system
                user_template = v.get("user_template") or user_template
                break

        return {
            "system": system,
            "user_template": user_template,
            "io_hints": io_hints,
            "prompt_rev": prompt_rev,
            "version": entry.get("version"),
        }

    # ── adapt → migrate → validate ────────────────────────────
    async def adapt_data(self, kind_or_alias: str, data: Dict[str, Any], *, version: Optional[str] = None) -> Dict[str, Any]:
        kd = await self._get_kind_doc(kind_or_alias)
        if not kd:
            raise ValueError(f"Unknown kind '{kind_or_alias}'")
        entry = await get_schema_version_entry(self.db, kd.id, version=version)
        if not entry:
            raise ValueError(f"Schema version not found for {kd.id}")

        out = json.loads(json.dumps(data))  # deep copy
        for ad in (entry.get("adapters") or []):
            ad_type = ad.get("type") or "builtin"
            if ad_type == "dsl" and ad.get("dsl"):
                out = _apply_adapter_dsl(out, ad["dsl"])
            # builtin adapter by id can be handled here later (whitelisted)
            # if ad_type == "builtin" and ad.get("ref"): call registered adapter
        return out

    async def migrate_data(
        self,
        kind_or_alias: str,
        data: Dict[str, Any],
        *,
        from_version: Optional[str],
        to_version: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], str]:
        """
        Applies a chain of migrators from from_version → target (latest by default).
        Returns (data_after, target_version)
        """
        kd = await self._get_kind_doc(kind_or_alias)
        if not kd:
            raise ValueError(f"Unknown kind '{kind_or_alias}'")
        target = to_version or kd.latest_schema_version
        if not from_version or from_version == target:
            return data, target

        # Find entries in order and walk migrators (only DSL supported here; builtins can be added)
        # We assume registry has a path via listed migrators; if not, we simply return input.
        cur_version = from_version
        cur_data = json.loads(json.dumps(data))
        safety_counter = 0
        while cur_version != target and safety_counter < 50:
            safety_counter += 1
            entry = await get_schema_version_entry(self.db, kd.id, version=cur_version)
            if not entry:
                break
            # Pick the migrator that leads closer to target (first match)
            next_version = None
            for mig in (entry.get("migrators") or []):
                if mig.get("from_version") == cur_version:
                    next_version = mig.get("to_version")
                    if mig.get("type") == "dsl" and mig.get("dsl"):
                        cur_data = _apply_adapter_dsl(cur_data, mig["dsl"])
                    # elif builtin: call builtin by id
                    break
            if not next_version:
                break
            cur_version = next_version

        return cur_data, cur_version

    async def validate_data(self, kind_or_alias: str, data: Dict[str, Any], *, version: Optional[str] = None) -> None:
        kd = await self._get_kind_doc(kind_or_alias)
        if not kd:
            raise ValueError(f"Unknown kind '{kind_or_alias}'")
        entry = await get_schema_version_entry(self.db, kd.id, version=version)
        if not entry:
            raise ValueError(f"Schema version not found for {kd.id}")
        schema = entry.get("json_schema")
        if not isinstance(schema, dict):
            raise ValueError("Invalid or missing json_schema")

        validator = _compile_validator(kd.id, entry["version"], schema)
        try:
            validator(data)
        except Exception as e:
            # Normalize error message
            msg = str(e)
            raise ValueError(f"Validation failed for {kd.id}@{entry['version']}: {msg}") from e

    # ── envelope assembly ─────────────────────────────────────
    async def build_envelope(
        self,
        *,
        kind_or_alias: str,
        name: str,
        data: Dict[str, Any],
        supplied_schema_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Returns a fully-normalized envelope ready to pass to Artifact DAL:
          { kind, name, data, natural_key, fingerprint, schema_version, summary, category }
        Steps:
           1) resolve kind & version, 2) migrate if needed, 3) adapt, 4) validate,
           5) compute NK/summary/category/fingerprint.
        """
        kd = await self._get_kind_doc(kind_or_alias)
        if not kd:
            raise ValueError(f"Unknown kind '{kind_or_alias}'")

        # 1/2) migrate to target (latest)
        migrated, at_version = await self.migrate_data(kd.id, data, from_version=supplied_schema_version, to_version=kd.latest_schema_version)

        # 3) adapters to canonicalize
        adapted = await self.adapt_data(kd.id, migrated, version=at_version)

        # 4) validate canonical data
        await self.validate_data(kd.id, adapted, version=at_version)

        # 5) identity + content hash
        entry = await get_schema_version_entry(self.db, kd.id, version=at_version)
        ident_spec = (entry or {}).get("identity") or {}
        natural_key = _compute_natural_key(kd.id, name, ident_spec, adapted)
        summary = _compute_summary(name, ident_spec, adapted)
        category = _compute_category(kd.id, kd)
        fingerprint = _sha256(_canonical(adapted))

        return {
            "kind": kd.id,
            "name": name,
            "data": adapted,
            "natural_key": natural_key,
            "fingerprint": fingerprint,
            "schema_version": at_version,
            "summary": summary,
            "category": category,
        }
