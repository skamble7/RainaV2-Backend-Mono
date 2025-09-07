# services/capability-registry/app/seeds/capabilities_seed.py
from __future__ import annotations

import os
import logging
from typing import List, Dict, Any, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase

from ..dal.capability_dal import ensure_indexes
from ..models.capability_pack import GlobalCapabilityCreate
from ..services.artifact_registry_client import ArtifactRegistryClient

logger = logging.getLogger("capability.seeds")

# Env flags:
# - CAPABILITIES_SEED_SKIP_IF_EXISTS: default "1" -> if collection has ≥1 doc, skip seeding
# - CAPABILITIES_SEED_VALIDATE_KINDS: default "0" -> optionally validate produces_kinds (non-blocking warnings)
SKIP_IF_EXISTS = os.getenv("CAPABILITIES_SEED_SKIP_IF_EXISTS", "1") not in ("0", "false", "False", "no", "NO")
VALIDATE_KINDS = os.getenv("CAPABILITIES_SEED_VALIDATE_KINDS", "0") in ("1", "true", "True", "yes", "YES")

# ---- Deduped capabilities extracted from your pack (svc-micro v1.4) ----
CAPABILITY_SEED: List[Dict[str, Any]] = [
    {
        "id": "cap.discover.context_map",
        "name": "Discover Context Map",
        "description": "Bounded contexts and relationships.",
        "tags": [],
        "parameters_schema": None,
        "produces_kinds": ["cam.diagram.context"],
        "agent": None,
    },
    {
        "id": "cap.data.dictionary",
        "name": "Domain Dictionary",
        "description": "Ubiquitous language and key terms.",
        "tags": [],
        "parameters_schema": None,
        "produces_kinds": ["cam.data.dictionary"],
        "agent": None,
    },
    {
        "id": "cap.catalog.services",
        "name": "Build Service Catalog",
        "description": "Service list with owners and interfaces.",
        "tags": [],
        "parameters_schema": None,
        "produces_kinds": ["cam.catalog.service"],
        "agent": None,
    },
    {
        "id": "cap.generate.class_diagram",
        "name": "Generate Class/ER Diagram",
        "description": "Core domain entities and relationships.",
        "tags": [],
        "parameters_schema": None,
        "produces_kinds": ["cam.diagram.class"],
        "agent": None,
    },
    {
        "id": "cap.diagram.activity",
        "name": "Key Flows (Activity)",
        "description": "End-to-end flows across services (BPMN-lite).",
        "tags": [],
        "parameters_schema": None,
        "produces_kinds": ["cam.diagram.activity"],
        "agent": None,
    },
    {
        "id": "cap.contracts.event",
        "name": "Event Contracts",
        "description": "Topics and schemas for async interactions.",
        "tags": [],
        "parameters_schema": None,
        "produces_kinds": ["cam.contract.event"],
        "agent": None,
    },
    {
        "id": "cap.contracts.api",
        "name": "API Contracts",
        "description": "REST/gRPC/GraphQL endpoints per service.",
        "tags": [],
        "parameters_schema": None,
        "produces_kinds": ["cam.contract.api"],
        "agent": None,
    },
    {
        "id": "cap.data.model",
        "name": "Logical Data Model",
        "description": "Entities and fields across the domain.",
        "tags": [],
        "parameters_schema": None,
        "produces_kinds": ["cam.data.model"],
        "agent": None,
    },
    {
        "id": "cap.diagram.deployment",
        "name": "Deployment View",
        "description": "Runtime nodes, connections, and envs.",
        "tags": [],
        "parameters_schema": None,
        "produces_kinds": ["cam.diagram.deployment"],
        "agent": None,
    },
    {
        "id": "cap.asset.service_inventory",
        "name": "Service Inventory",
        "description": "Canonical list of services.",
        "tags": [],
        "parameters_schema": None,
        "produces_kinds": ["cam.asset.service_inventory"],
        "agent": None,
    },
    {
        "id": "cap.asset.dependency_inventory",
        "name": "Dependency Inventory",
        "description": "Service-to-service dependencies.",
        "tags": [],
        "parameters_schema": None,
        "produces_kinds": ["cam.asset.dependency_inventory"],
        "agent": None,
    },
    {
        "id": "cap.asset.api_inventory",
        "name": "API Inventory",
        "description": "Flattened endpoint inventory by service.",
        "tags": [],
        "parameters_schema": None,
        "produces_kinds": ["cam.asset.api_inventory"],
        "agent": None,
    },
]

async def _maybe_validate_kinds(capabilities: List[Dict[str, Any]]):
    if not VALIDATE_KINDS:
        return
    client = ArtifactRegistryClient()
    kinds = []
    for c in capabilities:
        kinds.extend(c.get("produces_kinds") or [])
    kinds = list({k for k in kinds if k})
    if not kinds:
        return
    valid, invalid = await client.validate_kinds(kinds)
    if invalid:
        logger.warning(
            "Capability seed: some produces_kinds are not registered in artifact-service",
            extra={"invalid": invalid, "valid": valid},
        )


async def run_capabilities_seed(db: AsyncIOMotorDatabase):
    """
    Idempotent seed:
      - Ensures indexes
      - Skips if collection already has ≥1 doc (unless SKIP_IF_EXISTS is false)
      - Inserts this version of canonical/lean microservices capabilities
    """
    await ensure_indexes(db)

    existing_count = await db["capabilities"].count_documents({})
    if SKIP_IF_EXISTS and existing_count > 0:
        logger.info("Capabilities seed: skipped (collection already has records)", extra={"count": existing_count})
        return {"skipped": True, "existing": existing_count}

    # Optional validation (non-blocking; logs warnings)
    await _maybe_validate_kinds(CAPABILITY_SEED)

    # Upsert-like behavior: replace or insert by stable id
    # We intentionally do per-doc upserts to avoid partial failures with insert_many.
    inserted = 0
    replaced = 0
    for raw in CAPABILITY_SEED:
        doc = GlobalCapabilityCreate(**raw).model_dump()
        res = await db["capabilities"].find_one_and_replace(
            {"id": doc["id"]}, doc, upsert=True, return_document=True
        )
        # find_one_and_replace returns the *old* document if found; if not found, we can’t tell directly.
        # So check existence again (cheap due to index) to estimate action types:
        # (This is just for counters; correctness of upsert is guaranteed.)
        if res is None:
            inserted += 1
        else:
            replaced += 1

    total = await db["capabilities"].count_documents({})
    logger.info("Capabilities seed done", extra={"inserted": inserted, "replaced": replaced, "total": total})
    return {"skipped": False, "inserted": inserted, "replaced": replaced, "total": total}
