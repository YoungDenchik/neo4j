# # # agent/extractor.py
# # from __future__ import annotations

# # import json
# # from typing import Any, Dict, Optional, Type

# # from pydantic import BaseModel, ValidationError
# # from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# # from agent.openai_client import get_openai_client
# # from agent.json_schema import pydantic_to_json_schema
# # from agent.prompts import SYSTEM_EXTRACT


# # class LLMExtractionError(RuntimeError):
# #     pass


# # def _make_user_prompt(raw_json: Dict[str, Any], features: Optional[Dict[str, Any]] = None) -> str:
# #     return json.dumps(
# #         {
# #             "task": "Extract graph facts and return GraphFactsPayload JSON ONLY.",
# #             "raw_json": raw_json,
# #             "features": features or {},
# #         },
# #         ensure_ascii=False,
# #     )


# # @retry(
# #     reraise=True,
# #     stop=stop_after_attempt(3),
# #     wait=wait_exponential(multiplier=0.8, min=1, max=8),
# #     retry=retry_if_exception_type(LLMExtractionError),
# # )
# # def call_llm_extract(
# #     raw_json: Dict[str, Any],
# #     schema: Type[BaseModel],
# #     features: Optional[Dict[str, Any]] = None,
# # ) -> Any:
# #     """
# #     Uses OpenAI Structured Outputs: json_schema strict mode
# #     """
# #     client = get_openai_client()

# #     schema_json = pydantic_to_json_schema(schema)

# #     try:
# #         resp = client.responses.create(
# #             model="gpt-4o-mini",
# #             input=[
# #                 {"role": "system", "content": SYSTEM_EXTRACT},
# #                 {"role": "user", "content": _make_user_prompt(raw_json, features)},
# #             ],
# #             text={
# #                 "format": {
# #                     "type": "json_schema",
# #                     "json_schema": {
# #                         "name": "GraphFactsPayload",
# #                         "schema": schema_json,
# #                         "strict": True,
# #                     },
# #                 }
# #             },
# #         )
# #     except Exception as e:
# #         raise LLMExtractionError(f"OpenAI API call failed: {e}") from e

# #     # In Responses API, best helper:
# #     # resp.output_text contains final text.
# #     output_text = getattr(resp, "output_text", None)
# #     if not output_text:
# #         # fallback: try best-effort manual extraction
# #         raise LLMExtractionError("No output_text from OpenAI response")

# #     try:
# #         parsed = schema.model_validate_json(output_text)
# #         return parsed
# #     except ValidationError as e:
# #         raise LLMExtractionError(f"Schema validation failed: {e}") from e

# # agent/extractor.py
# from __future__ import annotations

# import json
# from typing import Any, Dict, Optional, Type

# from pydantic import BaseModel, ValidationError
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# from agent.openai_client import get_openai_client
# from agent.llm_config import get_llm_model
# from agent.prompts import SYSTEM_EXTRACT
# from agent.json_utils import extract_json_object, JsonExtractError


# class LLMExtractionError(RuntimeError):
#     pass


# def _make_user_prompt(raw_json: Dict[str, Any], features: Optional[Dict[str, Any]] = None) -> str:
#     return json.dumps(
#         {
#             "task": "Extract graph facts and return GraphFactsPayload JSON ONLY.",
#             "raw_json": raw_json,
#             "features": features or {},
#         },
#         ensure_ascii=False,
#     )


# @retry(
#     reraise=True,
#     stop=stop_after_attempt(3),
#     wait=wait_exponential(multiplier=0.8, min=1, max=8),
#     retry=retry_if_exception_type(LLMExtractionError),
# )
# def call_llm_extract(
#     raw_json: Dict[str, Any],
#     schema: Type[BaseModel],
#     features: Optional[Dict[str, Any]] = None,
# ) -> Any:
#     client = get_openai_client()
#     model = get_llm_model()

#     try:
#         resp = client.chat.completions.create(
#             model=model,
#             messages=[
#                 {"role": "system", "content": SYSTEM_EXTRACT},
#                 {"role": "user", "content": _make_user_prompt(raw_json, features)},
#             ],
#             temperature=0.0,
#             max_tokens=4000,
#         )
#     except Exception as e:
#         raise LLMExtractionError(f"LLM call failed: {e}") from e

#     text = resp.choices[0].message.content or ""

#     try:
#         obj = extract_json_object(text)
#     except JsonExtractError as e:
#         raise LLMExtractionError(f"Model did not return valid JSON: {e}. Raw output: {text[:400]}") from e

#     try:
#         return schema.model_validate(obj)
#     except ValidationError as e:
#         raise LLMExtractionError(f"Schema validation failed: {e}") from e

# agent/extractor.py
from __future__ import annotations

import json
from typing import Any, Dict, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from agent.openai_client import get_openai_client
from agent.llm_config import get_llm_model
from agent.prompts import SYSTEM_EXTRACT
from agent.json_utils import extract_json_object, JsonExtractError


class LLMExtractionError(RuntimeError):
    pass


T = TypeVar("T", bound=BaseModel)


def _make_user_prompt(raw_json: Dict[str, Any], features: Optional[Dict[str, Any]] = None) -> str:
    return json.dumps(
        {
            "task": "Extract graph facts and return GraphFactsPayload JSON ONLY. No markdown, no comments.",
            "raw_json": raw_json,
            "features": features or {},
        },
        ensure_ascii=False,
    )


def _validate_with_schema(schema: Type[T], obj: Any) -> T:
    """
    Supports both Pydantic v1 and v2.
    """
    if hasattr(schema, "model_validate"):  # Pydantic v2
        return schema.model_validate(obj)  # type: ignore[attr-defined]
    return schema.parse_obj(obj)  # type: ignore[return-value]


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.8, min=1, max=8),
    retry=retry_if_exception_type(LLMExtractionError),
)
def call_llm_extract(
    raw_json: Dict[str, Any],
    schema: Type[T],
    features: Optional[Dict[str, Any]] = None,
) -> T:
    client = get_openai_client()
    model = get_llm_model()

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_EXTRACT},
                {"role": "user", "content": _make_user_prompt(raw_json, features)},
            ],
            temperature=0.0,
            max_tokens=4000,
            # Якщо твій сервер це підтримує — увімкни:
            # response_format={"type": "json_object"},
        )
    except Exception as e:
        raise LLMExtractionError(f"LLM call failed: {e}") from e

    if not getattr(resp, "choices", None):
        raise LLMExtractionError("LLM returned empty choices list")

    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise LLMExtractionError("LLM returned empty message content")

    try:
        obj = extract_json_object(text)
    except JsonExtractError as e:
        raise LLMExtractionError(
            f"Model did not return valid JSON: {e}. Raw output: {text[:400]}"
        ) from e

    try:
        return _validate_with_schema(schema, obj)
    except ValidationError as e:
        # Це можна не ретраїти, якщо хочеш віддати в fixer:
        raise LLMExtractionError(f"Schema validation failed: {e}") from e
    except Exception as e:
        raise LLMExtractionError(f"Unexpected schema validation error: {e}") from e
