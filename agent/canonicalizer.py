# agent/canonicalizer.py
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict
from agent.schema import GraphFactsPayload


def _stable_hash(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def normalize(payload: GraphFactsPayload) -> GraphFactsPayload:
    """
    - ensure keys are str
    - ensure synthetic ids exist if needed
    """
    for n in payload.nodes:
        # convert all key_props/set_props keys to str
        n.key_props = {str(k): v for k, v in n.key_props.items()}
        n.set_props = {str(k): v for k, v in n.set_props.items()}

        # common patterns:
        if n.label == "Address" and "address_id" not in n.key_props:
            full = n.set_props.get("full_text") or n.key_props.get("full_text")
            if full:
                n.key_props["address_id"] = _stable_hash({"full_text": full})

        if n.label == "PersonAlias" and "alias_id" not in n.key_props:
            raw_name = n.set_props.get("full_name_raw") or ""
            dob = n.set_props.get("date_birth")
            n.key_props["alias_id"] = _stable_hash({"name": raw_name, "dob": dob})

    return payload
