# agent/schema.py
from __future__ import annotations

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


class NodeRef(BaseModel):
    label: str = Field(..., description="Node label from NodeLabel enum")
    id_value: str = Field(..., description="Stable identity value (rnokpp/edrpou/etc.)")


class FactNode(BaseModel):
    label: str
    key_props: Dict[str, Any]
    set_props: Dict[str, Any] = Field(default_factory=dict)


class FactRel(BaseModel):
    from_label: str
    from_id: str
    rel_type: str
    to_label: str
    to_id: str
    rel_props: Dict[str, Any] = Field(default_factory=dict)


class GraphFactsPayload(BaseModel):
    """
    Canonical payload that your Neo4j writer consumes.
    """
    nodes: List[FactNode] = Field(default_factory=list)
    rels: List[FactRel] = Field(default_factory=list)

    meta: Dict[str, Any] = Field(default_factory=dict)
