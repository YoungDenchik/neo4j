from __future__ import annotations
from typing import TypedDict, List, Dict, Any

from langgraph.graph import StateGraph, END

from domain.enums import NodeLabel, RelType
from repositories.ingest_repo import GraphRepository


class IngestionState(TypedDict):
    raw_record: Dict[str, Any]
    record_type: str
    facts: Dict[str, Any]
    is_valid: bool
    errors: List[str]


def detect_type_node(state: IngestionState) -> IngestionState:
    record = state["raw_record"]

    if "SourcesOfIncome" in record:
        state["record_type"] = "income"
    elif "Power_of_Attorney" in str(record):
        state["record_type"] = "poa"
    elif "activity_kinds" in str(record):
        state["record_type"] = "org_registry"
    else:
        state["record_type"] = "unknown"

    return state


def llm_extract_node(state: IngestionState) -> IngestionState:
    """
    Тут має бути твій LangChain LLM виклик.
    Поки що фейковий.
    """

    # TODO: call LLM with strict output schema
    state["facts"] = {
        "nodes": [],
        "relationships": []
    }
    return state


def validate_node(state: IngestionState) -> IngestionState:
    facts = state["facts"]
    errors: List[str] = []

    # basic validation
    if "nodes" not in facts or "relationships" not in facts:
        errors.append("facts must contain 'nodes' and 'relationships' keys")

    # validate nodes
    for n in facts.get("nodes", []):
        label = n.get("label")
        id_key = n.get("id_key")
        node_id = n.get("id")

        if label not in [x.value for x in NodeLabel]:
            errors.append(f"Invalid node label: {label}")

        # add more checks...

    # validate relationships
    for r in facts.get("relationships", []):
        rel_type = r.get("type")
        if rel_type not in [x.value for x in RelType]:
            errors.append(f"Invalid relationship type: {rel_type}")

    state["errors"] = errors
    state["is_valid"] = len(errors) == 0
    return state


def write_node(state: IngestionState) -> IngestionState:
    repo = GraphRepository()

    facts = state["facts"]

    # 1) merge nodes
    for n in facts.get("nodes", []):
        label = NodeLabel(n["label"])
        id_key = n["id_key"]
        node_id = n["id"]
        props = n.get("props", {})

        # Build merge payload:
        # key props = {id_key: node_id}
        key_props = {id_key: node_id}
        set_props = {**props, id_key: node_id}

        repo.merge_node(label=label, key_props=key_props, set_props=set_props)

    # 2) merge relationships
    for r in facts.get("relationships", []):
        rel_type = RelType(r["type"])

        from_node = r["from"]
        to_node = r["to"]

        from_label = NodeLabel(from_node["label"])
        to_label = NodeLabel(to_node["label"])

        repo.merge_relationship(
            from_label=from_label,
            from_id_value=from_node["id"],
            rel_type=rel_type,
            to_label=to_label,
            to_id_value=to_node["id"],
            rel_props=r.get("props", {}),
        )

    return state


def fix_with_llm_node(state: IngestionState) -> IngestionState:
    """
    Якщо валідатор знайшов помилки:
    -> просимо LLM виправити facts
    """
    # TODO: call LLM with errors + previous facts
    return state


def is_valid_router(state: IngestionState) -> str:
    return "write" if state["is_valid"] else "fix"


def build_ingestion_graph():
    g = StateGraph(IngestionState)

    g.add_node("detect_type", detect_type_node)
    g.add_node("llm_extract", llm_extract_node)
    g.add_node("validate", validate_node)
    g.add_node("write", write_node)
    g.add_node("fix", fix_with_llm_node)

    g.set_entry_point("detect_type")

    g.add_edge("detect_type", "llm_extract")
    g.add_edge("llm_extract", "validate")

    g.add_conditional_edges("validate", is_valid_router, {
        "write": "write",
        "fix": "fix",
    })

    g.add_edge("fix", "validate")
    g.add_edge("write", END)

    return g.compile()
