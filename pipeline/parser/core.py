import os
import re
import json

from openai import OpenAI
from dotenv import load_dotenv
from typing import List
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)


load_dotenv()

API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL")


class LLMParser:
    def __init__(self, model="lapa", temperature=0.0, max_tokens=None):
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model = model

        self.client = OpenAI(
            api_key=API_KEY,
            base_url=BASE_URL,
        )

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        text = text.strip()
        m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else text

    def _build_prompt(self, raw: str) -> str:
        return f"""
    You are a data extraction tool.

    Task:
    Extract business-relevant data from the input XML or JSON and return it as JSON.

    What to DROP (noise):
    - Transport / protocol wrappers (SOAP Envelope/Header/Body).
    - XML namespaces, schema locations, xsi/xsd technical attributes.
    - Authentication or security data (tokens, passwords, signatures, hashes).
    - Purely technical metadata (protocol versions, logging fields, pagination info).

    What to KEEP (important):
    - All business entities and their fields:
      persons, organizations, properties, income records, vehicles, requests,
      executors, powers of attorney, criteria, periods, etc.
    - ALL business identifiers and request context fields.
      Examples (not exhaustive): requestId, IDrequest, REQUESTID, VP, VPID,
      RNOKPP/IPN, EDRPOU, cadNum, regNum, rnNum, basis_request.

    Rules:
    1) Do NOT drop fields just because they look like request or correlation IDs.
       If a field identifies a business object or request, KEEP it.
    2) Remove a field only if it is clearly technical or security-related.
    3) Preserve original structure and arrays of business data.
    4) Do not invent, summarize, or reinterpret values.

    Output requirements:
    - Output ONLY valid JSON.
    - No markdown, no explanations.
    - Exact schema:

      {{
        "items": []
      }}

    Input:
    <<<
    {raw}
    >>>
    """.strip()

    def parse(self, text: str, id: str,) -> str:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Input text must be a non-empty string")

        messages: List[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(
                role="system",
                content="You extract structured data and output ONLY valid JSON. You never output secrets."
            ),
            ChatCompletionUserMessageParam(
                role="user",
                content=self._build_prompt(text)
            ),
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content or ""
        raw = self._strip_code_fences(raw)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            repair_messages: List[ChatCompletionMessageParam] = [
                ChatCompletionSystemMessageParam(
                    role="system",
                    content="Fix invalid JSON. Output ONLY valid JSON.",
                ),
                ChatCompletionUserMessageParam(
                    role="user",
                    content=raw,
                )
            ]

            response = self.client.chat.completions.create(
                model=self.model,
                messages=repair_messages,
                temperature=0.0,
                max_tokens=self.max_tokens,
            )

            raw = self._strip_code_fences(response.choices[0].message.content or "")
            parsed = json.loads(raw)

        if not isinstance(parsed, dict):
            raise ValueError("Parsed output is not a JSON object")

        if "items" not in parsed:
            raise ValueError("JSON does not match required schema")

        parsed["id"] = id

        return json.dumps(parsed, ensure_ascii=False)
