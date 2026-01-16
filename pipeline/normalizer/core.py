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
    Entities (all fields are strings unless otherwise noted):

    Person: {
      rnokpp: string (required),
      last_name: string (empty if missing),
      first_name: string (empty if missing),
      middle_name: string (nullable),
      date_birth: string (YYYY-MM-DD, nullable)
    }

    PersonAlias: {
      alias_id: string (required),
      full_name_raw: string (required),
      normalized_name: string (nullable),
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
      registration_date: string (YYYY-MM-DD, nullable),
      termination_date: string (YYYY-MM-DD, nullable)
    }

    Executor: {
      executor_rnokpp: string (nullable),
      executor_edrpou: string (nullable),
      full_name: string (empty if missing),
      position: string (nullable),
      department: string (nullable)
    }

    Request: {
      request_id: string (required),
      basis_request: string (nullable),
      application_number: string (nullable),
      application_date: string (YYYY-MM-DD, nullable),
      period_begin_month: number (nullable),
      period_begin_year: number (nullable),
      period_end_month: number (nullable),
      period_end_year: number (nullable),
      subject_rnokpp: string (nullable),
      executor_rnokpp: string (nullable)
    }

    IncomeRecord: {
      person_rnokpp: string (required),
      org_edrpou: string (required),
      income_id: string (required, constructed as person_rnokpp|org_edrpou|period_year|period_quarter_month|income_type_code),
      income_accrued: number (0 if missing),
      income_paid: number (0 if missing),
      tax_charged: number (0 if missing),
      tax_transferred: number (0 if missing),
      income_type_code: string (empty if missing),
      income_type_description: string (empty if missing),
      period_quarter_month: string (empty if missing),
      period_year: number (nullable),
      result_income: number (0 if missing),
      currency: string (default "UAH"),
      income_category: string (nullable),
      source_request_id: string (nullable)
    }

    Property: {
      property_id: string (required),
      owner_rnokpp: string (nullable),
      property_type: one of ["VEHICLE", "REAL_ESTATE", "OTHER", "LAND"],
      description: string (empty if missing),
      government_reg_number: string (nullable),
      serial_number: string (nullable),
      address_text: string (nullable),
      area: number (nullable),
      ownership_type: string (nullable),
      since_date: string (YYYY-MM-DD, nullable),
      source_request_id: string (nullable)
    }

    PowerOfAttorney: {
      poa_id: string (required, constructed as notarial_reg_number|attested_date|finished_date|witness_name),
      notarial_reg_number: string (nullable),
      attested_date: string (YYYY-MM-DD, nullable),
      finished_date: string (YYYY-MM-DD, nullable),
      witness_name: string (nullable),
      notary_name: string (nullable),
      grantor_rnokpp: string (nullable),
      representative_rnokpp: string (nullable),
      property: {
        property_type: string (nullable),
        description: string (empty if missing),
        government_reg_number: string (nullable),
        serial_number: string (nullable),
        address_text: string (nullable),
        area: number (nullable)
      },
      source_request_id: string (nullable)
    }

    NotarialBlank: {
      blank_id: string (required, constructed as serial|number),
      serial: string (nullable),
      number: string (nullable)
    }

    Document: {
      doc_id: string (required, constructed as doc_type|series|number|issued_by|issued_date),
      doc_type: string,
      series: string (nullable),
      number: string (nullable),
      issued_by: string (nullable),
      issued_date: string (YYYY-MM-DD, nullable),
      expiry_date: string (YYYY-MM-DD, nullable)
    }

    Relationships (each list belongs under "relationships"):
      director_of: { person_rnokpp: string, org_edrpou: string, role_text: string (nullable) }
      founder_of:  { person_rnokpp: string, org_edrpou: string, capital: number (nullable), role_text: string (nullable) }
      child_of:    { child_rnokpp: string, parent_rnokpp: string }
      spouse_of:   { person1_rnokpp: string, person2_rnokpp: string, marriage_date: string (YYYY-MM-DD, nullable) }
      earned_income: { person_rnokpp: string, income_id: string }
      paid_by:     { income_id: string, org_edrpou: string }
      owns:        { person_rnokpp: string, property_id: string, ownership_type: string (nullable), since_date: string (YYYY-MM-DD, nullable) }
      has_grantor: { poa_id: string, grantor_rnokpp: string }
      has_representative: { poa_id: string, representative_rnokpp: string }
      has_property: { poa_id: string, property_id: string }
      has_notarial_blank: { poa_id: string, blank_id: string }
      created_by:  { request_id: string, executor_rnokpp: string }
      about:       { request_id: string, subject_rnokpp: string }
      provided:    { request_id: string, node_label: string, node_id: string }

    Output JSON:
    {
      "persons": [],
      "person_aliases": [],
      "organizations": [],
      "executors": [],
      "requests": [],
      "income_records": [],
      "properties": [],
      "power_of_attorney": [],
      "notarial_blanks": [],
      "documents": [],
      "relationships": {
        "director_of": [],
        "founder_of": [],
        "child_of": [],
        "spouse_of": [],
        "earned_income": [],
        "paid_by": [],
        "owns": [],
        "has_grantor": [],
        "has_representative": [],
        "has_property": [],
        "has_notarial_blank": [],
        "created_by": [],
        "about": [],
        "provided": []
      }
    }
    """.strip()

        input_json = json.dumps(item, ensure_ascii=False)

        return (
            "You are a normalization agent.\n"
            "Convert the input JSON into domain entities and relationships.\n"
            "STRICT: output ONLY valid JSON matching the schema. Do not invent values.\n\n"
            f"{entity_definitions}\n\n"
            "RULES (STRICT):\n"
            "1) Canonical request id (TOP-LEVEL ONLY):\n"
            "- Let top_id = input JSON top-level field \"id\".\n"
            "- If top_id starts with \"З-\" and does NOT contain \"#\":\n"
            "  * request_id = top_id; emit exactly ONE Request.\n"
            "- Else if top_id starts with \"В-\" and does NOT contain \"#\":\n"
            "  * request_id = replace leading \"В-\" with \"З-\"; emit exactly ONE Request.\n"
            "- Else:\n"
            "  * No valid request_id exists.\n"
            "  * Do NOT emit Request, about, created_by, or provided.\n"
            "  * For all entities: source_request_id = null.\n"
            "- NEVER derive request_id from notarial_reg_number, poa_id, blank_id, property_id, income_id, or numbers.\n\n"
            "2) PROVIDED (MANDATORY when request_id exists):\n"
            "- ONLY if request_id exists:\n"
            "  * For EVERY emitted entity (Person, PersonAlias, Organization, Executor, IncomeRecord, Property,\n"
            "    PowerOfAttorney, NotarialBlank, Document):\n"
            "    - If the entity has source_request_id field → set it to request_id.\n"
            "    - Add EXACTLY ONE relationships.provided entry:\n"
            "      { \"request_id\": request_id, \"node_label\": \"<EntityType>\", \"node_id\": \"<entity primary id>\" }\n"
            "- Objects of this shape are ALLOWED ONLY in relationships.provided.\n\n"
            "3) Request relationships:\n"
            "- created_by: { request_id, executor_rnokpp } ONLY if executor_rnokpp is present.\n"
            "- about: { request_id, subject_rnokpp } ONLY if subject_rnokpp is present.\n\n"
            "4) Person vs PersonAlias:\n"
            "- Person.rnokpp MUST be a non-empty string.\n"
            "- If rnokpp is missing → DO NOT create Person; create PersonAlias instead.\n\n"
            "5) Income:\n"
            "- For each tax agent → create Organization and link via paid_by.\n"
            "- income_category mapping:\n"
            "  101→SALARY, 102→CONTRACT, 157→BUSINESS, 195→RENT,\n"
            "  128→SOCIAL, 150→SCHOLARSHIP, 126→BONUS_BENEFIT, else OTHER.\n\n"
            "6) Power of Attorney:\n"
            "- Embedded properties are NOT owned assets.\n"
            "- Do NOT emit owns for them.\n"
            "- Use only has_grantor, has_representative, has_property, has_notarial_blank.\n\n"
            "7) Property ID:\n"
            "- property_id format:\n"
            "  property_type|description|government_reg_number|serial_number|address_text|area\n"
            "- The description MUST be real (make/model/year), not a generic category.\n"
            "- For missing components INSIDE property_id ONLY → use literal string \"null\".\n\n"
            "8) Null handling:\n"
            "- Use JSON null for missing nullable fields.\n"
            "- The string \"null\" is FORBIDDEN outside property_id.\n\n"
            "9) No guessing:\n"
            "- Never invent ids, dates, names, numbers.\n"
            "- Never copy basis_request into application_number.\n\n"
            f"INPUT JSON:\n{input_json}\n\n"
            "Return ONLY the normalized JSON object."
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
