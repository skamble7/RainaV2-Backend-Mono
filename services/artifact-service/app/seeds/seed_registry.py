# services/artifact-service/app/seeds/seed_registry.py
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.db.mongodb import get_db
from app.dal.kind_registry_dal import upsert_kind

LATEST = "1.0.0"

# ─────────────────────────────────────────────────────────────
# Canonical list (exactly what you asked for)
# ─────────────────────────────────────────────────────────────
ALL_KINDS: List[str] = [
    # 2.1 Diagrams
    "cam.diagram.context","cam.diagram.class","cam.diagram.sequence","cam.diagram.component",
    "cam.diagram.deployment","cam.diagram.state","cam.diagram.activity","cam.diagram.dataflow","cam.diagram.network",
    # 2.2 PAT
    "cam.pat.moscow_prioritization","cam.pat.requirements_traceability_matrix","cam.pat.stakeholder_map",
    "cam.pat.assumptions_log","cam.pat.constraints_log","cam.pat.value_stream_map",
    # 2.3 DAM
    "cam.dam.raci","cam.dam.crud","cam.dam.dependency_matrix","cam.dam.coupling_matrix","cam.dam.quality_attribute_scenarios",
    # 2.4 Contracts
    "cam.contract.api","cam.contract.event","cam.contract.schema","cam.contract.service",
    # 2.5 Capability & Domain Models
    "cam.model.capability","cam.model.domain","cam.catalog.service",
    # 2.6 Workflows & Orchestration
    "cam.workflow.process","cam.workflow.state_machine","cam.workflow.saga","cam.workflow.batch_job","cam.workflow.pipeline",
    # 2.7 Security & Compliance
    "cam.security.policy","cam.security.threat_model","cam.security.trust_boundary","cam.security.control_matrix",
    # 2.8 Data & Information Architecture
    "cam.data.model","cam.data.lineage","cam.data.retention_policy","cam.data.dictionary","cam.data.privacy_matrix",
    # 2.9 Infrastructure & Deployment
    "cam.infra.topology","cam.infra.environment","cam.infra.k8s_manifest","cam.infra.network_policy",
    "cam.infra.scaling_policy","cam.infra.backup_restore",
    # 2.10 Observability & SLOs
    "cam.obs.metrics_catalog","cam.obs.logging_plan","cam.obs.tracing_map","cam.obs.dashboard",
    "cam.obs.slo_objectives","cam.obs.alerting_policy",
    # 2.11 Governance & Decisions
    "cam.gov.adr.index","cam.gov.adr.record","cam.gov.standards","cam.gov.compliance_matrix",
    # 2.12 Risk Management
    "cam.risk.register","cam.risk.matrix","cam.risk.mitigation_plan",
    # 2.13 Operations & Runbooks
    "cam.ops.runbook","cam.ops.playbook","cam.ops.postmortem","cam.ops.oncall_roster",
    # 2.14 FinOps / Cost
    "cam.finops.cost_model","cam.finops.budget","cam.finops.usage_report","cam.finops.chargeback_policy",
    # 2.15 QA / Testing
    "cam.qa.test_plan","cam.qa.test_cases","cam.qa.coverage_matrix","cam.qa.defect_density_matrix","cam.qa.performance_report",
    # 2.16 Performance & Capacity
    "cam.perf.benchmark_report","cam.perf.capacity_plan","cam.perf.load_profile","cam.perf.tuning_guidelines",
    # 2.17 Asset & Inventory (CMDB-lite)
    "cam.asset.service_inventory","cam.asset.dependency_inventory","cam.asset.api_inventory",
]

ALIASES: Dict[str, List[str]] = {
    "cam.diagram.class": ["cam.erd"],
    "cam.contract.api": ["cam.api_contracts", "ext.legacy.openapi_doc"],
    "cam.gov.adr.index": ["cam.adr_index"],
}

# ─────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────
def category_of(kind: str) -> str:
    parts = kind.split(".")
    return parts[1] if len(parts) >= 3 else "misc"

def artifact_of(kind: str) -> str:
    return kind.split(".")[-1]

def doc_type_for(kind: str) -> str:
    # canonical doc_type string to embed in schemas
    return artifact_of(kind)

PROMPT_DEFAULT = {
    "system": (
        "You are RAINA: Artifact Generator. Return a single JSON object that conforms "
        "to the provided schema. No prose, no comments, no explanations. Use only keys "
        "from the schema and omit unknowns."
    ),
    "user_template": (
        "Inputs: {{ inputs | tojson }}\n"
        "Params: {{ params | tojson }}\n"
        "Schema: {{ schema | tojson }}\n"
        "Now produce exactly one JSON object."
    ),
    "io_hints": {"type": "object"},
    "strict_json": True,
    "prompt_rev": 1,
}

def prompt_for_family(family: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = default or PROMPT_DEFAULT
    if family == "diagram":
        return {
            **base,
            "system": (
                "You are RAINA: Diagram Extractor. Identify nodes and edges appropriate for the diagram type. "
                "Return EXACTLY one JSON object following the schema. No prose."
            ),
        }
    if family == "pat":
        return {
            **base,
            "system": (
                "You are RAINA: Planning Tools Agent. Produce structured tables/lists for the requested PAT artifact. "
                "Return EXACTLY one JSON object following the schema. No prose."
            ),
        }
    if family == "dam":
        return {
            **base,
            "system": (
                "You are RAINA: Architecture Matrix Agent. Produce matrices with explicit rows, columns, and cells. "
                "Return EXACTLY one JSON object following the schema. No prose."
            ),
        }
    if family == "contract":
        return {
            **base,
            "system": (
                "You are RAINA: Interface Contracts Agent. Produce minimal, consistent contracts. "
                "Return EXACTLY one JSON object; prefer concise fields."
            ),
        }
    if family in {"model", "catalog"}:
        return {**base, "system": "You are RAINA: Modeling Agent. Return one JSON object per schema. No prose."}
    if family == "workflow":
        return {**base, "system": "You are RAINA: Workflow Agent. Return one JSON object following the schema."}
    if family == "security":
        return {**base, "system": "You are RAINA: Security Agent. Return one JSON object following the schema."}
    if family == "data":
        return {**base, "system": "You are RAINA: Data Architecture Agent. Return one JSON object following the schema."}
    if family == "infra":
        return {**base, "system": "You are RAINA: Infrastructure Agent. Return one JSON object following the schema."}
    if family == "obs":
        return {**base, "system": "You are RAINA: Observability Agent. Return one JSON object following the schema."}
    if family == "gov":
        return {**base, "system": "You are RAINA: Governance Agent. Return one JSON object following the schema."}
    if family == "risk":
        return {**base, "system": "You are RAINA: Risk Agent. Return one JSON object following the schema."}
    if family == "ops":
        return {**base, "system": "You are RAINA: Operations Agent. Return one JSON object following the schema."}
    if family == "finops":
        return {**base, "system": "You are RAINA: FinOps Agent. Return one JSON object following the schema."}
    if family == "qa":
        return {**base, "system": "You are RAINA: QA Agent. Return one JSON object following the schema."}
    if family == "perf":
        return {**base, "system": "You are RAINA: Performance Agent. Return one JSON object following the schema."}
    if family == "asset":
        return {**base, "system": "You are RAINA: Inventory Agent. Return one JSON object following the schema."}
    return base

SCHEMA_STRING = "https://json-schema.org/draft/2020-12/schema"

def obj(props: Dict[str, Any], *, req: Optional[List[str]] = None, addl: bool = False) -> Dict[str, Any]:
    return {"$schema": SCHEMA_STRING, "type": "object", "properties": props, "required": req or [], "additionalProperties": addl}

def arr(items: Dict[str, Any], *, min_items: int = 0) -> Dict[str, Any]:
    return {"type": "array", "items": items, "minItems": min_items}

def str_enum(vals: List[str]) -> Dict[str, Any]:
    return {"type": "string", "enum": vals}

def simple_kv(value_type: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "object", "additionalProperties": value_type}

# ─────────────────────────────────────────────────────────────
# Family schema builders (concise but useful)
# ─────────────────────────────────────────────────────────────
def schema_diagram(kind: str) -> Dict[str, Any]:
    art = artifact_of(kind)
    base_node = obj({
        "id": {"type": "string"},
        "name": {"type": "string"},
        "type": {"type": "string"},
        "meta": {"type": "object", "additionalProperties": True},
    }, req=["id","name"], addl=False)
    base_edge = obj({
        "from": {"type": "string"},
        "to": {"type": "string"},
        "label": {"type": "string"},
        "meta": {"type": "object", "additionalProperties": True},
    }, req=["from","to"], addl=False)

    props = {
        "doc_type": {"const": art},
        "nodes": arr(base_node),
        "edges": arr(base_edge),
        "notes": {"type": "string"},
    }

    # Specializations
    if art == "class":
        attr = obj({"name":{"type":"string"},"type":{"type":"string"},"pk":{"type":"boolean"},"nullable":{"type":"boolean"}}, req=["name","type"], addl=False)
        ent = obj({
            "id":{"type":"string"},
            "name":{"type":"string"},
            "attributes": arr(attr),
            "meta": {"type":"object","additionalProperties": True}
        }, req=["id","name"], addl=False)
        rel = obj({
            "from":{"type":"string"},
            "to":{"type":"string"},
            "cardinality": str_enum(["1:1","1:N","N:M"]),
            "label":{"type":"string"}
        }, req=["from","to"], addl=False)
        props.update({"entities": arr(ent), "relationships": arr(rel)})
    elif art == "sequence":
        lifeline = obj({"id":{"type":"string"},"name":{"type":"string"},"role":{"type":"string"}}, req=["id","name"], addl=False)
        msg = obj({"from":{"type":"string"},"to":{"type":"string"},"message":{"type":"string"},"async":{"type":"boolean"}}, req=["from","to","message"], addl=False)
        props.update({"lifelines": arr(lifeline), "messages": arr(msg)})
    elif art == "component":
        comp = obj({"id":{"type":"string"},"name":{"type":"string"},"layer":{"type":"string"},"tech":{"type":"string"}}, req=["id","name"], addl=False)
        dep = obj({"from":{"type":"string"},"to":{"type":"string"},"type":{"type":"string"}}, req=["from","to"], addl=False)
        props.update({"components": arr(comp), "dependencies": arr(dep)})
    elif art == "deployment":
        node = obj({"id":{"type":"string"},"name":{"type":"string"},"kind":{"enum":["server","pod","node","gateway","db","cache","queue","mesh","function"]},"zone":{"type":"string"}}, req=["id","name"], addl=False)
        conn = obj({"from":{"type":"string"},"to":{"type":"string"},"protocol":{"type":"string"},"port":{"type":["integer","string"]}}, req=["from","to"], addl=False)
        props.update({"environment": {"type":"string"}, "nodes": arr(node), "connections": arr(conn)})
    elif art == "state":
        st = obj({"id":{"type":"string"},"name":{"type":"string"},"type":{"enum":["initial","normal","final"]}}, req=["id","name"], addl=False)
        tr = obj({"from":{"type":"string"},"to":{"type":"string"},"event":{"type":"string"},"guard":{"type":"string"}}, req=["from","to","event"], addl=False)
        props.update({"states": arr(st, min_items=1), "transitions": arr(tr)})
    elif art == "activity":
        act = obj({"id":{"type":"string"},"name":{"type":"string"},"kind":{"enum":["task","gateway","event"]}}, req=["id","name"], addl=False)
        flow = obj({"from":{"type":"string"},"to":{"type":"string"},"condition":{"type":"string"}}, req=["from","to"], addl=False)
        props.update({"activities": arr(act, min_items=1), "flows": arr(flow)})
    elif art == "dataflow":
        proc = obj({"id":{"type":"string"},"name":{"type":"string"}}, req=["id","name"], addl=False)
        store = obj({"id":{"type":"string"},"name":{"type":"string"}}, req=["id","name"], addl=False)
        flow = obj({"from":{"type":"string"},"to":{"type":"string"},"data":{"type":"string"}}, req=["from","to","data"], addl=False)
        props.update({"processes": arr(proc), "stores": arr(store), "flows": arr(flow)})
    elif art == "network":
        vpc = obj({"id":{"type":"string"},"cidr":{"type":"string"}}, req=["id","cidr"], addl=False)
        subnet = obj({"id":{"type":"string"},"cidr":{"type":"string"},"vpc_id":{"type":"string"}}, req=["id","cidr","vpc_id"], addl=False)
        route = obj({"from":{"type":"string"},"to":{"type":"string"},"target":{"type":"string"}}, req=["from","to","target"], addl=False)
        props.update({"vpcs": arr(vpc), "subnets": arr(subnet), "routes": arr(route)})

    return obj(props, req=["doc_type"], addl=False)

def schema_pat(kind: str) -> Dict[str, Any]:
    art = artifact_of(kind)
    if art == "moscow_prioritization":
        item = obj({"id":{"type":"string"},"title":{"type":"string"},"priority": str_enum(["must","should","could","won't"]), "rationale":{"type":"string"}}, req=["title","priority"], addl=False)
        return obj({"doc_type":{"const":art},"items": arr(item)}, req=["doc_type","items"], addl=False)
    if art == "requirements_traceability_matrix":
        row = obj({"requirement_id":{"type":"string"},"story_keys": arr({"type":"string"}),"tests": arr({"type":"string"}),"status": str_enum(["planned","in_progress","done"])}, req=["requirement_id"], addl=False)
        return obj({"doc_type":{"const":art},"rows": arr(row)}, req=["doc_type","rows"], addl=False)
    if art == "stakeholder_map":
        stake = obj({"name":{"type":"string"},"role":{"type":"string"},"influence": str_enum(["low","medium","high"]), "interest": str_enum(["low","medium","high"])}, req=["name"], addl=False)
        return obj({"doc_type":{"const":art},"stakeholders": arr(stake)}, req=["doc_type","stakeholders"], addl=False)
    if art == "assumptions_log":
        rec = obj({"id":{"type":"string"},"assumption":{"type":"string"},"validated":{"type":"boolean"},"impact":{"type":"string"}}, req=["assumption"], addl=False)
        return obj({"doc_type":{"const":art},"entries": arr(rec)}, req=["doc_type","entries"], addl=False)
    if art == "constraints_log":
        rec = obj({"id":{"type":"string"},"constraint":{"type":"string"},"type": str_enum(["technical","business","regulatory"]),"notes":{"type":"string"}}, req=["constraint"], addl=False)
        return obj({"doc_type":{"const":art},"entries": arr(rec)}, req=["doc_type","entries"], addl=False)
    if art == "value_stream_map":
        step = obj({"name":{"type":"string"},"lead_time":{"type":"number"},"value_added":{"type":"boolean"}}, req=["name"], addl=False)
        return obj({"doc_type":{"const":art},"steps": arr(step),"metrics": simple_kv({"type":["string","number"]})}, req=["doc_type","steps"], addl=False)
    return obj({"doc_type":{"const":art}}, req=["doc_type"], addl=True)

def schema_dam(kind: str) -> Dict[str, Any]:
    art = artifact_of(kind)
    cell = obj({"row":{"type":"string"},"col":{"type":"string"},"value":{"type":["string","number","boolean","null"]}}, req=["row","col"], addl=False)
    base = {"doc_type":{"const":art},"rows": arr({"type":"string"}),"cols": arr({"type":"string"}),"cells": arr(cell)}
    if art == "crud":
        base["entities"] = arr({"type":"string"})
        base["operations"] = arr(str_enum(["C","R","U","D"]))
    if art == "raci":
        base["roles"] = arr({"type":"string"})
        base["responsibilities"] = arr({"type":"string"})
    return obj(base, req=["doc_type","rows","cols","cells"], addl=False)

def schema_contract(kind: str) -> Dict[str, Any]:
    art = artifact_of(kind)
    if art == "api":
        ep = obj({
            "method": str_enum(["GET","POST","PUT","DELETE","PATCH","HEAD","OPTIONS"]),
            "path": {"type":"string"},
            "summary":{"type":"string"},
            "request_schema":{"type":"object"},
            "response_schema":{"type":"object"},
            "auth": obj({"required":{"type":"boolean"},"scopes": arr({"type":"string"})}, req=["required"], addl=False),
        }, req=["method","path"], addl=False)
        svc = obj({"name":{"type":"string"},"style": str_enum(["rest","grpc","graphql"]),"openapi":{"type":["string","null"]},"grpc_idl":{"type":["string","null"]},"endpoints": arr(ep),"story_keys": arr({"type":"string"})}, req=["name","style"], addl=False)
        return obj({"doc_type":{"const":"api_contracts"},"services": arr(svc)}, req=["services"], addl=False)
    if art == "event":
        topic = obj({"name":{"type":"string"},"schema":{"type":"object"},"retention":{"type":"string"},"compaction":{"type":"boolean"}}, req=["name","schema"], addl=False)
        return obj({"doc_type":{"const":"event_contracts"},"topics": arr(topic)}, req=["topics"], addl=False)
    if art == "schema":
        ref = obj({"name":{"type":"string"},"format": str_enum(["json_schema","avro","protobuf","xsd"]),"definition":{"type":"object"}}, req=["name","format","definition"], addl=False)
        return obj({"doc_type":{"const":"shared_schemas"},"definitions": arr(ref)}, req=["definitions"], addl=False)
    if art == "service":
        sla = obj({"availability":{"type":"string"},"latency_ms":{"type":"number"},"throughput":{"type":"string"}}, addl=False)
        return obj({"doc_type":{"const":"service_contract"},"targets": sla, "dependencies": arr({"type":"string"}), "interfaces": arr({"type":"string"})}, req=["doc_type"], addl=False)
    return obj({"doc_type":{"const":art}}, req=["doc_type"], addl=True)

def schema_model_catalog(kind: str) -> Dict[str, Any]:
    art = artifact_of(kind)
    if art == "capability":
        cap = obj({"id":{"type":"string"},"name":{"type":"string"},"level":{"type":"integer"},"parent_id":{"type":["string","null"]}}, req=["name","level"], addl=False)
        return obj({"doc_type":{"const":art},"capabilities": arr(cap)}, req=["doc_type","capabilities"], addl=False)
    if art == "domain":
        term = obj({"term":{"type":"string"},"definition":{"type":"string"},"synonyms": arr({"type":"string"})}, req=["term","definition"], addl=False)
        return obj({"doc_type":{"const":art},"glossary": arr(term)}, req=["doc_type","glossary"], addl=False)
    if art == "service":  # cam.catalog.service
        svc = obj({"name":{"type":"string"},"owner":{"type":"string"},"tier": str_enum(["critical","high","medium","low"]),"interfaces": arr({"type":"string"})}, req=["name","owner"], addl=False)
        return obj({"doc_type":{"const":art},"services": arr(svc)}, req=["doc_type","services"], addl=False)
    return obj({"doc_type":{"const":art}}, req=["doc_type"], addl=True)

def schema_workflow(kind: str) -> Dict[str, Any]:
    art = artifact_of(kind)
    if art == "process":
        step = obj({"id":{"type":"string"},"name":{"type":"string"},"owner":{"type":"string"}}, req=["id","name"], addl=False)
        trans = obj({"from":{"type":"string"},"to":{"type":"string"},"condition":{"type":"string"}}, req=["from","to"], addl=False)
        return obj({"doc_type":{"const":art},"steps": arr(step),"transitions": arr(trans)}, req=["doc_type","steps"], addl=False)
    if art == "state_machine":
        return schema_diagram("cam.diagram.state")  # reuse
    if art == "saga":
        st = obj({"name":{"type":"string"},"type": str_enum(["choreography","orchestration"])}, req=["name","type"], addl=False)
        act = obj({"name":{"type":"string"},"compensating_action":{"type":"string"}}, req=["name"], addl=False)
        return obj({"doc_type":{"const":art},"stages": arr(st),"actions": arr(act)}, req=["doc_type","stages"], addl=False)
    if art == "batch_job":
        job = obj({"name":{"type":"string"},"schedule":{"type":"string"},"retries":{"type":"integer"}}, req=["name"], addl=False)
        return obj({"doc_type":{"const":art},"jobs": arr(job)}, req=["doc_type","jobs"], addl=False)
    if art == "pipeline":
        stg = obj({"name":{"type":"string"},"type":{"type":"string"},"config":{"type":"object"}}, req=["name","type"], addl=False)
        return obj({"doc_type":{"const":art},"stages": arr(stg),"artifacts": arr({"type":"string"})}, req=["doc_type","stages"], addl=False)
    return obj({"doc_type":{"const":art}}, req=["doc_type"], addl=True)

def schema_security(kind: str) -> Dict[str, Any]:
    art = artifact_of(kind)
    if art == "policy":
        role = obj({"name":{"type":"string"},"scopes": arr({"type":"string"})}, req=["name"], addl=False)
        return obj({"doc_type":{"const":art},"roles": arr(role),"rules": simple_kv({"type":"string"})}, req=["doc_type"], addl=False)
    if art == "threat_model":
        threat = obj({"id":{"type":"string"},"title":{"type":"string"},"stride": arr(str_enum(["S","T","R","I","D","E"])),"severity": str_enum(["low","medium","high","critical"])}, req=["id","title"], addl=False)
        return obj({"doc_type":{"const":art},"threats": arr(threat)}, req=["doc_type","threats"], addl=False)
    if art == "trust_boundary":
        zone = obj({"id":{"type":"string"},"name":{"type":"string"},"data_classes": arr({"type":"string"})}, req=["id","name"], addl=False)
        boundary = obj({"from":{"type":"string"},"to":{"type":"string"},"controls": arr({"type":"string"})}, req=["from","to"], addl=False)
        return obj({"doc_type":{"const":art},"zones": arr(zone),"boundaries": arr(boundary)}, req=["doc_type","zones"], addl=False)
    if art == "control_matrix":
        return schema_dam("cam.dam.dependency_matrix")
    return obj({"doc_type":{"const":art}}, req=["doc_type"], addl=True)

def schema_data(kind: str) -> Dict[str, Any]:
    art = artifact_of(kind)
    if art == "model":
        field = obj({"name":{"type":"string"},"type":{"type":"string"},"nullable":{"type":"boolean"}}, req=["name","type"], addl=False)
        entity = obj({"name":{"type":"string"},"fields": arr(field)}, req=["name","fields"], addl=False)
        return obj({"doc_type":{"const":art},"entities": arr(entity)}, req=["doc_type","entities"], addl=False)
    if art == "lineage":
        edge = obj({"from":{"type":"string"},"to":{"type":"string"},"field":{"type":"string"}}, req=["from","to"], addl=False)
        return obj({"doc_type":{"const":art},"edges": arr(edge)}, req=["doc_type","edges"], addl=False)
    if art == "retention_policy":
        rule = obj({"dataset":{"type":"string"},"retention":{"type":"string"},"delete_after_days":{"type":"integer"}}, req=["dataset","retention"], addl=False)
        return obj({"doc_type":{"const":art},"rules": arr(rule)}, req=["doc_type","rules"], addl=False)
    if art == "dictionary":
        term = obj({"name":{"type":"string"},"type":{"type":"string"},"description":{"type":"string"}}, req=["name","type"], addl=False)
        return obj({"doc_type":{"const":art},"terms": arr(term)}, req=["doc_type","terms"], addl=False)
    if art == "privacy_matrix":
        row = obj({"dataset":{"type":"string"},"pii_class":{"type":"string"},"handling":{"type":"string"}}, req=["dataset","pii_class"], addl=False)
        return obj({"doc_type":{"const":art},"rows": arr(row)}, req=["doc_type","rows"], addl=False)
    return obj({"doc_type":{"const":art}}, req=["doc_type"], addl=True)

def schema_infra(kind: str) -> Dict[str, Any]:
    art = artifact_of(kind)
    if art == "topology":
        res = obj({"id":{"type":"string"},"type":{"type":"string"},"name":{"type":"string"},"labels": simple_kv({"type":"string"})}, req=["id","type","name"], addl=False)
        rel = obj({"from":{"type":"string"},"to":{"type":"string"},"kind":{"type":"string"}}, req=["from","to"], addl=False)
        return obj({"doc_type":{"const":art},"resources": arr(res),"relations": arr(rel)}, req=["doc_type","resources"], addl=False)
    if art == "environment":
        env = obj({"name":{"type":"string"},"purpose":{"type":"string"},"drift_policy":{"type":"string"}}, req=["name"], addl=False)
        return obj({"doc_type":{"const":art},"environments": arr(env)}, req=["doc_type","environments"], addl=False)
    if art == "k8s_manifest":
        man = obj({"kind":{"type":"string"},"apiVersion":{"type":"string"},"metadata":{"type":"object"},"spec":{"type":"object"}}, req=["kind","apiVersion"], addl=True)
        return obj({"doc_type":{"const":art},"manifests": arr(man)}, req=["doc_type","manifests"], addl=False)
    if art == "network_policy":
        pol = obj({"name":{"type":"string"},"namespace":{"type":"string"},"ingress":{"type":"object"},"egress":{"type":"object"}}, req=["name"], addl=True)
        return obj({"doc_type":{"const":art},"policies": arr(pol)}, req=["doc_type","policies"], addl=False)
    if art == "scaling_policy":
        pol = obj({"target":{"type":"string"},"metric":{"type":"string"},"threshold":{"type":"number"},"min":{"type":"integer"},"max":{"type":"integer"}}, req=["target","metric","threshold"], addl=False)
        return obj({"doc_type":{"const":art},"policies": arr(pol)}, req=["doc_type","policies"], addl=False)
    if art == "backup_restore":
        plan = obj({"name":{"type":"string"},"rpo":{"type":"string"},"rto":{"type":"string"},"schedule":{"type":"string"},"targets": arr({"type":"string"})}, req=["name"], addl=False)
        return obj({"doc_type":{"const":art},"plans": arr(plan)}, req=["doc_type","plans"], addl=False)
    return obj({"doc_type":{"const":art}}, req=["doc_type"], addl=True)

def schema_obs(kind: str) -> Dict[str, Any]:
    art = artifact_of(kind)
    if art == "metrics_catalog":
        metric = obj({"name":{"type":"string"},"owner":{"type":"string"},"sli":{"type":"string"},"unit":{"type":"string"}}, req=["name"], addl=False)
        return obj({"doc_type":{"const":art},"metrics": arr(metric)}, req=["doc_type","metrics"], addl=False)
    if art == "logging_plan":
        event = obj({"name":{"type":"string"},"level": str_enum(["debug","info","warn","error"]),"retention_days":{"type":"integer"},"redact":{"type":"boolean"}}, req=["name","level"], addl=False)
        return obj({"doc_type":{"const":art},"events": arr(event)}, req=["doc_type","events"], addl=False)
    if art == "tracing_map":
        span = obj({"name":{"type":"string"},"service":{"type":"string"},"critical_path":{"type":"boolean"}}, req=["name","service"], addl=False)
        return obj({"doc_type":{"const":art},"spans": arr(span)}, req=["doc_type","spans"], addl=False)
    if art == "dashboard":
        dash = obj({"name":{"type":"string"},"panels": arr({"type":"string"}),"owner":{"type":"string"}}, req=["name"], addl=False)
        return obj({"doc_type":{"const":art},"dashboards": arr(dash)}, req=["doc_type","dashboards"], addl=False)
    if art == "slo_objectives":
        slo = obj({"service":{"type":"string"},"sli":{"type":"string"},"target":{"type":"number"},"window":{"type":"string"}}, req=["service","sli","target"], addl=False)
        return obj({"doc_type":{"const":art},"slos": arr(slo)}, req=["doc_type","slos"], addl=False)
    if art == "alerting_policy":
        alert = obj({"name":{"type":"string"},"condition":{"type":"string"},"threshold":{"type":"number"},"runbook":{"type":"string"}}, req=["name","condition"], addl=False)
        return obj({"doc_type":{"const":art},"alerts": arr(alert)}, req=["doc_type","alerts"], addl=False)
    return obj({"doc_type":{"const":art}}, req=["doc_type"], addl=True)

def schema_gov(kind: str) -> Dict[str, Any]:
    art = artifact_of(kind)
    if art == "adr.index":
        entry = obj({"id":{"type":"string"},"title":{"type":"string"},"status": str_enum(["proposed","accepted","rejected","superseded"])}, req=["id","title"], addl=False)
        return obj({"doc_type":{"const":"adr_index"},"entries": arr(entry)}, req=["doc_type","entries"], addl=False)
    if art == "adr.record":
        rec = obj({"id":{"type":"string"},"title":{"type":"string"},"context":{"type":"string"},"decision":{"type":"string"},"status": str_enum(["proposed","accepted","rejected","superseded"])}, req=["id","title","decision"], addl=False)
        return obj({"doc_type":{"const":"adr_record"},"record": rec}, req=["doc_type","record"], addl=False)
    if art == "standards":
        std = obj({"name":{"type":"string"},"category":{"type":"string"},"status": str_enum(["approved","deprecated","experimental"])}, req=["name","status"], addl=False)
        return obj({"doc_type":{"const":art},"standards": arr(std)}, req=["doc_type","standards"], addl=False)
    if art == "compliance_matrix":
        row = obj({"control":{"type":"string"},"evidence":{"type":"string"},"owner":{"type":"string"},"status": str_enum(["na","planned","in_progress","complete"])}, req=["control","status"], addl=False)
        return obj({"doc_type":{"const":art},"rows": arr(row)}, req=["doc_type","rows"], addl=False)
    return obj({"doc_type":{"const":art}}, req=["doc_type"], addl=True)

def schema_risk(kind: str) -> Dict[str, Any]:
    art = artifact_of(kind)
    if art == "register":
        item = obj({"id":{"type":"string"},"title":{"type":"string"},"probability": str_enum(["low","medium","high"]),"impact": str_enum(["low","medium","high"]),"owner":{"type":"string"},"status":{"type":"string"}}, req=["id","title","probability","impact"], addl=False)
        return obj({"doc_type":{"const":art},"risks": arr(item)}, req=["doc_type","risks"], addl=False)
    if art == "matrix":
        cell = obj({"prob":{"type":"string"},"impact":{"type":"string"},"count":{"type":"integer"}}, req=["prob","impact"], addl=False)
        return obj({"doc_type":{"const":art},"cells": arr(cell)}, req=["doc_type","cells"], addl=False)
    if art == "mitigation_plan":
        step = obj({"risk_id":{"type":"string"},"action":{"type":"string"},"owner":{"type":"string"},"due":{"type":"string"},"status":{"type":"string"}}, req=["risk_id","action"], addl=False)
        return obj({"doc_type":{"const":art},"steps": arr(step)}, req=["doc_type","steps"], addl=False)
    return obj({"doc_type":{"const":art}}, req=["doc_type"], addl=True)

def schema_ops(kind: str) -> Dict[str, Any]:
    art = artifact_of(kind)
    if art == "runbook":
        step = obj({"order":{"type":"integer"},"instruction":{"type":"string"},"check":{"type":"string"}}, req=["order","instruction"], addl=False)
        return obj({"doc_type":{"const":art},"steps": arr(step)}, req=["doc_type","steps"], addl=False)
    if art == "playbook":
        scen = obj({"name":{"type":"string"},"triggers": arr({"type":"string"}),"actions": arr({"type":"string"})}, req=["name"], addl=False)
        return obj({"doc_type":{"const":art},"scenarios": arr(scen)}, req=["doc_type","scenarios"], addl=False)
    if art == "postmortem":
        sec = obj({"incident_id":{"type":"string"},"impact":{"type":"string"},"root_cause":{"type":"string"},"actions": arr({"type":"string"})}, req=["incident_id"], addl=False)
        return obj({"doc_type":{"const":art},"report": sec}, req=["doc_type","report"], addl=False)
    if art == "oncall_roster":
        ent = obj({"team":{"type":"string"},"rotation":{"type":"string"},"members": arr({"type":"string"})}, req=["team","members"], addl=False)
        return obj({"doc_type":{"const":art},"rosters": arr(ent)}, req=["doc_type","rosters"], addl=False)
    return obj({"doc_type":{"const":art}}, req=["doc_type"], addl=True)

def schema_finops(kind: str) -> Dict[str, Any]:
    art = artifact_of(kind)
    if art == "cost_model":
        drv = obj({"name":{"type":"string"},"metric":{"type":"string"},"weight":{"type":"number"}}, req=["name","metric"], addl=False)
        return obj({"doc_type":{"const":art},"drivers": arr(drv)}, req=["doc_type","drivers"], addl=False)
    if art == "budget":
        bud = obj({"period":{"type":"string"},"amount":{"type":"number"},"owner":{"type":"string"}}, req=["period","amount"], addl=False)
        return obj({"doc_type":{"const":art},"budgets": arr(bud)}, req=["doc_type","budgets"], addl=False)
    if art == "usage_report":
        rec = obj({"period":{"type":"string"},"service":{"type":"string"},"usage":{"type":"number"},"cost":{"type":"number"}}, req=["period","service"], addl=False)
        return obj({"doc_type":{"const":art},"records": arr(rec)}, req=["doc_type","records"], addl=False)
    if art == "chargeback_policy":
        pol = obj({"rule":{"type":"string"},"allocation":{"type":"string"}}, req=["rule","allocation"], addl=False)
        return obj({"doc_type":{"const":art},"policies": arr(pol)}, req=["doc_type","policies"], addl=False)
    return obj({"doc_type":{"const":art}}, req=["doc_type"], addl=True)

def schema_qa(kind: str) -> Dict[str, Any]:
    art = artifact_of(kind)
    if art == "test_plan":
        plan = obj({"name":{"type":"string"},"scope":{"type":"string"},"strategy":{"type":"string"}}, req=["name"], addl=False)
        return obj({"doc_type":{"const":art},"plan": plan}, req=["doc_type","plan"], addl=False)
    if art == "test_cases":
        case = obj({"id":{"type":"string"},"title":{"type":"string"},"steps": arr({"type":"string"}),"expected":{"type":"string"}}, req=["id","title"], addl=False)
        return obj({"doc_type":{"const":art},"cases": arr(case)}, req=["doc_type","cases"], addl=False)
    if art == "coverage_matrix":
        cell = obj({"component":{"type":"string"},"area":{"type":"string"},"coverage":{"type":"number"}}, req=["component","area"], addl=False)
        return obj({"doc_type":{"const":art},"cells": arr(cell)}, req=["doc_type","cells"], addl=False)
    if art == "defect_density_matrix":
        row = obj({"component":{"type":"string"},"loc":{"type":"integer"},"defects":{"type":"integer"}}, req=["component","loc","defects"], addl=False)
        return obj({"doc_type":{"const":art},"rows": arr(row)}, req=["doc_type","rows"], addl=False)
    if art == "performance_report":
        met = obj({"metric":{"type":"string"},"value":{"type":"number"},"unit":{"type":"string"}}, req=["metric","value"], addl=False)
        return obj({"doc_type":{"const":art},"metrics": arr(met)}, req=["doc_type","metrics"], addl=False)
    return obj({"doc_type":{"const":art}}, req=["doc_type"], addl=True)

def schema_perf(kind: str) -> Dict[str, Any]:
    art = artifact_of(kind)
    if art == "benchmark_report":
        run = obj({"name":{"type":"string"},"scenario":{"type":"string"},"results": simple_kv({"type":["number","string"]})}, req=["name"], addl=False)
        return obj({"doc_type":{"const":art},"runs": arr(run)}, req=["doc_type","runs"], addl=False)
    if art == "capacity_plan":
        entry = obj({"resource":{"type":"string"},"current":{"type":"number"},"forecast":{"type":"number"}}, req=["resource","current","forecast"], addl=False)
        return obj({"doc_type":{"const":art},"entries": arr(entry)}, req=["doc_type","entries"], addl=False)
    if art == "load_profile":
        point = obj({"timestamp":{"type":"string"},"load":{"type":"number"}}, req=["timestamp","load"], addl=False)
        return obj({"doc_type":{"const":art},"series": arr(point)}, req=["doc_type","series"], addl=False)
    if art == "tuning_guidelines":
        rec = obj({"area":{"type":"string"},"recommendation":{"type":"string"}}, req=["area","recommendation"], addl=False)
        return obj({"doc_type":{"const":art},"guidelines": arr(rec)}, req=["doc_type","guidelines"], addl=False)
    return obj({"doc_type":{"const":art}}, req=["doc_type"], addl=True)

def schema_asset(kind: str) -> Dict[str, Any]:
    art = artifact_of(kind)
    if art == "service_inventory":
        svc = obj({"name":{"type":"string"},"owner":{"type":"string"},"lifecycle": str_enum(["design","alpha","beta","ga","retired"])}, req=["name","owner"], addl=False)
        return obj({"doc_type":{"const":art},"services": arr(svc)}, req=["doc_type","services"], addl=False)
    if art == "dependency_inventory":
        dep = obj({"from":{"type":"string"},"to":{"type":"string"},"type":{"type":"string"}}, req=["from","to"], addl=False)
        return obj({"doc_type":{"const":art},"dependencies": arr(dep)}, req=["doc_type","dependencies"], addl=False)
    if art == "api_inventory":
        ep = obj({"service":{"type":"string"},"method":{"type":"string"},"path":{"type":"string"}}, req=["service","method","path"], addl=False)
        return obj({"doc_type":{"const":art},"endpoints": arr(ep)}, req=["doc_type","endpoints"], addl=False)
    return obj({"doc_type":{"const":art}}, req=["doc_type"], addl=True)

# Router of family → schema builder
FAMILY_BUILDERS = {
    "diagram": schema_diagram,
    "pat": schema_pat,
    "dam": schema_dam,
    "contract": schema_contract,
    "model": schema_model_catalog,
    "catalog": schema_model_catalog,
    "workflow": schema_workflow,
    "security": schema_security,
    "data": schema_data,
    "infra": schema_infra,
    "obs": schema_obs,
    "gov": schema_gov,
    "risk": schema_risk,
    "ops": schema_ops,
    "finops": schema_finops,
    "qa": schema_qa,
    "perf": schema_perf,
    "asset": schema_asset,
}

def family_of(kind: str) -> str:
    return category_of(kind)

def prompt_for(kind: str) -> Dict[str, Any]:
    return prompt_for_family(family_of(kind))

def schema_for(kind: str) -> Dict[str, Any]:
    fam = family_of(kind)
    fn = FAMILY_BUILDERS.get(fam)
    return fn(kind) if fn else obj({"doc_type":{"const":doc_type_for(kind)}}, req=["doc_type"], addl=True)

def identity_for(kind: str) -> Dict[str, Any]:
    # Keep identity simple: use envelope name; specialized families can be refined later.
    return {"natural_key": ["name"], "summary_rule": "{{name}}", "category": family_of(kind)}

def build_kind_doc(kind: str) -> Dict[str, Any]:
    return {
        "_id": kind,
        "title": artifact_of(kind).replace("_"," ").title(),
        "summary": f"Canonical artifact for {kind}",
        "category": family_of(kind),
        "aliases": ALIASES.get(kind, []),
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": schema_for(kind),
                "additional_props_policy": "forbid",
                "prompt": prompt_for(kind),
                "identity": identity_for(kind),
                "adapters": [],
                "migrators": [],
                "examples": [],
            }
        ],
        "policies": {},
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

# ─────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────
async def main():
    db = await get_db()
    count = 0
    for k in ALL_KINDS:
        doc = build_kind_doc(k)
        await upsert_kind(db, doc)
        count += 1
    print(f"Seeded/updated {count} kinds to registry.")

if __name__ == "__main__":
    asyncio.run(main())
