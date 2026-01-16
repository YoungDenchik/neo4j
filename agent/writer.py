# agent/writer.py
from __future__ import annotations

from agent.schema import GraphFactsPayload
from domain.enums import NodeLabel, RelType
from repositories.ingest_repo import GraphRepository


def persist_to_neo4j(payload: GraphFactsPayload, repo: GraphRepository) -> None:
    # 1) nodes
    for node in payload.nodes:
        repo.merge_node(
            label=NodeLabel(node.label),
            key_props=node.key_props,
            set_props=node.set_props,
        )

    # 2) relationships
    for rel in payload.rels:
        repo.merge_relationship(
            from_label=NodeLabel(rel.from_label),
            from_id_value=rel.from_id,
            rel_type=RelType(rel.rel_type),
            to_label=NodeLabel(rel.to_label),
            to_id_value=rel.to_id,
            rel_props=rel.rel_props,
        )
