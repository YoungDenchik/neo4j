# agent/validator.py
from __future__ import annotations

from typing import List
from domain.enums import NodeLabel, RelType


def validate(payload) -> List[str]:
    errors: List[str] = []

    allowed_labels = {e.value for e in NodeLabel}
    allowed_rels = {e.value for e in RelType}

    # Nodes
    for i, n in enumerate(payload.nodes):
        if n.label not in allowed_labels:
            errors.append(f"nodes[{i}].label='{n.label}' is not allowed")

        if not n.key_props:
            errors.append(f"nodes[{i}].key_props is empty")

    # Rels
    for i, r in enumerate(payload.rels):
        if r.from_label not in allowed_labels:
            errors.append(f"rels[{i}].from_label='{r.from_label}' is not allowed")

        if r.to_label not in allowed_labels:
            errors.append(f"rels[{i}].to_label='{r.to_label}' is not allowed")

        if r.rel_type not in allowed_rels:
            errors.append(f"rels[{i}].rel_type='{r.rel_type}' is not allowed")

        if not r.from_id:
            errors.append(f"rels[{i}].from_id is empty")

        if not r.to_id:
            errors.append(f"rels[{i}].to_id is empty")

    return errors
