# services/discovery-service/app/graphs/discovery_graph.py

from langgraph.graph import StateGraph, END
from typing import Callable
from app.models.state import DiscoveryState
from app.agents.ingest_node import ingest_node
from app.agents.plan_node import plan_node
from app.agents.pipeline.generate_node import generate_node
from app.agents.validate_node import validate_node
from app.agents.persist_node import persist_node
from app.agents.publish_node import publish_node

def build_graph() -> Callable[[DiscoveryState], DiscoveryState]:
    sg = StateGraph(DiscoveryState)
    sg.add_node("ingest", ingest_node)
    sg.add_node("plan", plan_node)
    sg.add_node("generate", generate_node)
    sg.add_node("validate", validate_node)
    sg.add_node("persist", persist_node)
    sg.add_node("publish", publish_node)

    sg.set_entry_point("ingest")
    sg.add_edge("ingest", "plan")
    sg.add_edge("plan", "generate")
    sg.add_edge("generate", "validate")
    sg.add_edge("validate", "persist")
    sg.add_edge("persist", "publish")
    sg.add_edge("publish", END)

    return sg.compile()
