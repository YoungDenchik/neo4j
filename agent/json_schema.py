# agent/json_schema.py
from __future__ import annotations

from typing import Type
from pydantic import BaseModel


def pydantic_to_json_schema(model: Type[BaseModel]) -> dict:
    """
    Pydantic v2: model.model_json_schema()
    """
    return model.model_json_schema()
