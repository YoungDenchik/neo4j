import json
import os
import re
from typing import Dict, Optional

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

load_dotenv()

API_KEY: Optional[str] = os.getenv("API_KEY")
BASE_URL: Optional[str] = os.getenv("BASE_URL")


class LLMNormalizer:
    def __init__(
        self,
        model: str = "lapa",
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        self.client = OpenAI(
            api_key=API_KEY,
            base_url=BASE_URL,
        )

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        text = text.strip()
        m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else text

    def _build_prompt(self, item: Dict) -> str:
        entity_definitions = """
        Entities and attributes (all fields are strings unless otherwise noted):
        
        Person: {
          rnokpp: string (required),
          last_name: string (empty if missing),
          first_name: string (empty if missing),
          middle_name: string (nullable),
          date_birth: string (YYYY-MM-DD, nullable)
        }
        
        Organization: {
          edrpou: string (required),
          name: string (empty if missing),
          short_name: string (nullable),
          state: string (nullable),
          state_text: string (nullable),
          olf_code: string (nullable),
          olf_name: string (nullable),
          authorised_capital: number (nullable),
          registration_date: string (YYYY-MM-DD, nullable)
        }
        
        IncomeRecord: {
          person_rnokpp: string (required),
          org_edrpou: string (required),
          income_accrued: number (0 if missing),
          income_paid: number (0 if missing),
          tax_charged: number (0 if missing),
          tax_transferred: number (0 if missing),
          income_type_code: string (empty if missing),
          income_type_description: string (empty if missing),
          period_quarter_month: string (empty if missing),
          period_year: number (nullable),
          result_income: number (0 if missing)
        }
        
        Property: {
          owner_rnokpp: string (required),
          property_type: one of ["VEHICLE", "REAL_ESTATE", "UNKNOWN"],
          description: string (empty if missing),
          government_reg_number: string (nullable),
          serial_number: string (nullable),
          address: string (nullable),
          area: number (nullable),
          ownership_type: string (nullable),
          since_date: string (YYYY-MM-DD, nullable)
        }
        
        Request: {
          request_id: string (required),
          basis_request: string (nullable),
          application_number: string (nullable),
          application_date: string (nullable),
          period_begin_month: number (nullable),
          period_begin_year: number (nullable),
          period_end_month: number (nullable),
          period_end_year: number (nullable),
          subject_rnokpp: string (nullable),
          executor_rnokpp: string (nullable)
        }
        
        Executor: {
          executor_rnokpp: string (required),
          executor_edrpou: string (nullable),
          full_name: string (empty if missing)
        }
        
        PowerOfAttorney: {
          notarial_reg_number: string (nullable),
          attested_date: string (nullable),
          finished_date: string (nullable),
          witness_name: string (nullable),
          grantor_rnokpp: string (nullable),
          representative_rnokpp: string (nullable),
          property: {
            property_type: string (nullable),
            description: string (empty if missing),
            government_reg_number: string (nullable),
            serial_number: string (nullable),
            address: string (nullable),
            area: number (nullable)
          }
        }
        
        Relationships:
          - DIRECTOR_OF: {"person_rnokpp", "org_edrpou", "role_text"}
          - FOUNDER_OF: {"person_rnokpp", "org_edrpou", "capital", "role_text"}
          - CHILD_OF: {"child_rnokpp", "parent_rnokpp"}
          - SPOUSE_OF: {"person1_rnokpp", "person2_rnokpp", "marriage_date"}
        
        Output JSON:
        {
          "persons": [],
          "organizations": [],
          "income_records": [],
          "properties": [],
          "requests": [],
          "executors": [],
          "power_of_attorney": [],
          "relations": []
        }
        """
        input_json = json.dumps(item, ensure_ascii=False)
        return (
            "You are a normalisation agent."
            " Map the input business data into the defined domain entities and relationships."
            " Only include fields that are present in the schema; ignore everything else."
            f"\n\n{entity_definitions}\n\n"
            f"Input item JSON:\n{input_json}\n\n"
            "Respond with the normalised JSON as specified."
        )

    def normalize(self, item: Dict) -> Dict:
        if not isinstance(item, dict):
            raise ValueError("Input item must be a dictionary")

        messages: list[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(
                role="system",
                content="You extract structured data and output ONLY valid JSON.",
            ),
            ChatCompletionUserMessageParam(
                role="user",
                content=self._build_prompt(item),
            ),
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"},
        )

        raw = self._strip_code_fences(response.choices[0].message.content or "")
        data = json.loads(raw)

        if not isinstance(data, dict):
            raise ValueError("Output must be a JSON object")

        return data
