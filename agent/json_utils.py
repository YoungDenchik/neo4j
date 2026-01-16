# agent/json_utils.py
from __future__ import annotations

import json
import re
from typing import Any, Dict


class JsonExtractError(ValueError):
    pass


def extract_json_object(text: str) -> Dict[str, Any]:
    """
    Extract first JSON object {...} from model output.
    Works even if model adds text before/after JSON.
    """
    if not text or not isinstance(text, str):
        raise JsonExtractError("Empty or non-string output")

    text = text.strip()

    # remove ``` fences
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    # If already pure JSON
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Find first {...} block (greedy but ok for single JSON object)
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        raise JsonExtractError("No JSON object found in output")

    candidate = m.group(0)

    # remove trailing commas
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise JsonExtractError(f"JSON parse failed: {e}") from e
