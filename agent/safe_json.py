# agent/safe_json.py
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Union


class RawJsonParseError(ValueError):
    pass


def _strip_code_fences(s: str) -> str:
    s = s.strip()
    # ```json ... ```
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s)
    return s.strip()


def safe_parse_raw_input(raw: Any) -> Union[Dict[str, Any], List[Any]]:
    """
    Accepts:
      - dict -> returns dict
      - list -> returns list
      - str  -> tries to json.loads
    Also attempts small repairs for common broken JSON cases.
    """
    if raw is None:
        raise RawJsonParseError("raw input is None")

    if isinstance(raw, (dict, list)):
        return raw

    if isinstance(raw, str):
        s = _strip_code_fences(raw)

        # quick repair: replace single quotes with double quotes (very risky, but common)
        # only if it *looks like* JSON object/array but uses single quotes
        looks_like_json = (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]"))
        if looks_like_json and "'" in s and '"' not in s:
            s = s.replace("'", '"')

        # remove trailing commas: { "a": 1, }
        s = re.sub(r",\s*([}\]])", r"\1", s)

        try:
            return json.loads(s)
        except json.JSONDecodeError as e:
            raise RawJsonParseError(f"Invalid JSON string: {e}") from e

    raise RawJsonParseError(f"Unsupported raw input type: {type(raw)}")
