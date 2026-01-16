# # llm/fixer.py
# from __future__ import annotations

# from typing import Any, Dict, List, Optional

# from graph_facts.schema import GraphFactsPayload, ValidationErrorItem
# from llm.prompts import FIX_SYSTEM_PROMPT, build_fix_prompt

# from openai import OpenAI


# class GraphFactsFixer:
#     """
#     Fixes a broken GraphFactsPayload using LLM based on validator errors.
#     """

#     def __init__(
#         self,
#         client: Optional[OpenAI] = None,
#         model: str = "gpt-4o-mini",
#         temperature: float = 0.0,
#     ):
#         self.client = client or OpenAI()
#         self.model = model
#         self.temperature = temperature

#     def fix(self, payload: GraphFactsPayload, errors: List[ValidationErrorItem]) -> GraphFactsPayload:
#         payload_json = payload.model_dump(by_alias=True)
#         errors_json = [e.model_dump() for e in errors]

#         user_prompt = build_fix_prompt(payload_json=payload_json, errors=errors_json)

#         resp = self.client.responses.parse(
#             model=self.model,
#             input=[
#                 {"role": "system", "content": FIX_SYSTEM_PROMPT},
#                 {"role": "user", "content": user_prompt},
#             ],
#             temperature=self.temperature,
#             text_format=GraphFactsPayload,
#         )

#         return resp.output_parsed


# # agent/fixer.py
# from __future__ import annotations

# import json
# from typing import List

# from pydantic import ValidationError

# from agent.openai_client import get_openai_client
# from agent.json_schema import pydantic_to_json_schema
# from agent.prompts import FIX_PROMPT
# from agent.schema import GraphFactsPayload


# class LLMFixError(RuntimeError):
#     pass


# def call_llm_fix(facts: GraphFactsPayload, errors: List[str]) -> GraphFactsPayload:
#     client = get_openai_client()

#     payload = {
#         "facts": facts.model_dump(),
#         "validation_errors": errors,
#         "task": "Fix the facts payload so it is valid GraphFactsPayload JSON.",
#     }

#     schema_json = pydantic_to_json_schema(GraphFactsPayload)

#     try:
#         resp = client.responses.create(
#             model="gpt-4o-mini",
#             input=[
#                 {"role": "system", "content": FIX_PROMPT},
#                 {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
#             ],
#             text={
#                 "format": {
#                     "type": "json_schema",
#                     "json_schema": {
#                         "name": "GraphFactsPayload",
#                         "schema": schema_json,
#                         "strict": True,
#                     },
#                 }
#             },
#         )
#     except Exception as e:
#         raise LLMFixError(f"OpenAI API call failed: {e}") from e

#     out = getattr(resp, "output_text", None)
#     if not out:
#         raise LLMFixError("No output_text from OpenAI response")

#     try:
#         return GraphFactsPayload.model_validate_json(out)
#     except ValidationError as e:
#         raise LLMFixError(f"Fixed payload still invalid: {e}") from e

# agent/fixer.py
from __future__ import annotations

import json
from typing import List

from pydantic import ValidationError

from agent.openai_client import get_openai_client
from agent.llm_config import get_fix_model
from agent.prompts import FIX_PROMPT
from agent.schema import GraphFactsPayload
from agent.json_utils import extract_json_object, JsonExtractError


class LLMFixError(RuntimeError):
    pass


def call_llm_fix(facts: GraphFactsPayload, errors: List[str]) -> GraphFactsPayload:
    client = get_openai_client()
    model = get_fix_model()

    payload = {
        "task": "Fix GraphFactsPayload JSON ONLY.",
        "facts": facts.model_dump(),
        "validation_errors": errors,
    }

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": FIX_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=3000,
        )
    except Exception as e:
        raise LLMFixError(f"LLM fix call failed: {e}") from e

    text = resp.choices[0].message.content or ""

    try:
        obj = extract_json_object(text)
    except JsonExtractError as e:
        raise LLMFixError(f"Fixer did not return valid JSON: {e}. Raw output: {text[:400]}") from e

    try:
        return GraphFactsPayload.model_validate(obj)
    except ValidationError as e:
        raise LLMFixError(f"Fixed payload still invalid: {e}") from e
