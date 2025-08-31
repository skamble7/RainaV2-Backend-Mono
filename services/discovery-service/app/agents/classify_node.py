from __future__ import annotations

from typing import Any, Dict, List, Tuple
from app.models.state import DiscoveryState
from app.clients import artifact_service

def _nk(a: Dict[str, Any]) -> str:
    return (a.get("natural_key") or f"{a.get('kind')}:{a.get('name')}").lower().strip()

def _index_by_nk(docs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for d in docs or []:
        if isinstance(d, dict):
            nk = _nk(d)
            if nk:
                out[nk] = d
    return out

def _finger(d: Dict[str, Any]) -> Tuple[str, str]:
    # Prefer persistent identity, else content hash-like fingerprint
    aid = str(d.get("artifact_id") or d.get("_id") or "")
    fp = str(d.get("fingerprint") or "")
    return aid, fp

async def classify_node(state: DiscoveryState) -> DiscoveryState:
    """
    Classify current run's artifacts vs baseline snapshot in artifact-service:

      new:       present in run, not in baseline
      updated:   present in both (by natural_key), but different id/fingerprint
      unchanged: present in both with same id or fingerprint
      retired:   present in baseline, missing in run

    Writes:
      - state["run_artifacts"]  (exact artifacts produced this run, pre-persist)
      - state["artifacts_diff"] (lists + counts)
      - state["deltas"]         (counts mirror for convenience)
    """
    workspace_id = state.get("workspace_id")
    strategy = (state.get("strategy") or "delta").lower().strip()

    # Artifacts produced by the generate phase (pre-persist)
    run_artifacts: List[Dict[str, Any]] = list(state.get("artifacts") or [])
    state["run_artifacts"] = run_artifacts  # aid: persisted by main if desired

    # Baseline snapshot from artifact-service (current workspace head)
    base_docs: List[Dict[str, Any]] = []
    try:
        parent = await artifact_service.get_workspace_with_artifacts(workspace_id, include_deleted=False)
        base_docs = list((parent or {}).get("artifacts") or [])
    except Exception as e:
        state.setdefault("logs", []).append(f"classify: baseline fetch failed: {e}")

    # Baseline strategy → everything is 'new'
    if strategy == "baseline":
        nks = sorted({_nk(a) for a in run_artifacts})
        counts = {"new": len(nks), "updated": 0, "unchanged": 0, "retired": 0, "deleted": 0}
        state["artifacts_diff"] = {"new": nks, "updated": [], "unchanged": [], "retired": [], "counts": counts}
        state["deltas"] = {"counts": dict(counts)}
        state.setdefault("logs", []).append(f"classify: baseline run → counts={counts}")
        return state

    L = _index_by_nk(base_docs)       # baseline (left)
    R = _index_by_nk(run_artifacts)   # this run (right)

    new_keys: List[str] = []
    upd_keys: List[str] = []
    same_keys: List[str] = []
    ret_keys: List[str] = []

    for nk, r in R.items():
        l = L.get(nk)
        if not l:
            new_keys.append(nk)
            continue
        lid, lfp = _finger(l)
        rid, rfp = _finger(r)
        if (lid and rid and lid == rid) or (lfp and rfp and lfp == rfp):
            same_keys.append(nk)
        else:
            upd_keys.append(nk)

    for nk in L.keys():
        if nk not in R:
            ret_keys.append(nk)

    counts = {
        "new": len(new_keys),
        "updated": len(upd_keys),
        "unchanged": len(same_keys),
        "retired": len(ret_keys),
        "deleted": 0,  # reserved for future logical deletions
    }
    artdiff = {
        "new": sorted(new_keys),
        "updated": sorted(upd_keys),
        "unchanged": sorted(same_keys),
        "retired": sorted(ret_keys),
        "counts": counts,
    }

    state["artifacts_diff"] = artdiff
    state["deltas"] = {"counts": dict(counts)}
    state.setdefault("logs", []).append(f"classify: counts={counts} (L={len(L)} R={len(R)})")
    return state
