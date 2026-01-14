from __future__ import annotations

import hashlib
import json
from typing import Dict, Any, Optional

from domain.models import (
    Person,
    Organization,
    IncomeRecord,
    Property,
    Request,
    Executor,
    PowerOfAttorney,
)
from domain.enums import PropertyType
from repositories.registry_repo import RegistryRepository
from repositories.mutation_repo import GraphMutationRepository


class IngestionService:
    """
    Facts → Graph (ingestion layer).

    RESPONSIBILITIES:
    - Parse raw JSON data from source files
    - Transform into domain entities
    - Merge entities via RegistryRepository (identity)
    - Create relationships via GraphMutationRepository (facts)
    - Handle synthetic ID generation for entities without natural keys

    WHY: Separates data parsing/transformation from graph operations.
    Business logic lives here, not in repositories.

    DESIGN PRINCIPLE: This service knows about source data structure.
    It transforms messy real-world data into clean domain objects.
    """

    def __init__(
        self,
        registry_repo: RegistryRepository,
        mutation_repo: GraphMutationRepository,
    ):
        self.registry = registry_repo
        self.mutation = mutation_repo

    # ========================================================================
    # High-level ingestion methods (full record processing)
    # ========================================================================

    def ingest_json_record(self, json_line: str) -> None:
        """
        Ingest a single JSON record from all_data.txt.
        WHY: Each line is a complete investigative record with multiple entity types.
        This method dispatches to appropriate handlers based on content.
        """
        try:
            data = json.loads(json_line)
            items = data.get("items", [])
            record_id = data.get("id", "unknown")

            for item in items:
                # Dispatch based on content (heuristic detection)
                if "RNOKPP" in item and "SourcesOfIncome" in item:
                    self._ingest_income_data(item, record_id)
                elif "person" in item and "ExecutorInfo" in item:
                    self._ingest_request_data(item, record_id)
                elif "code" in item and "founders" in item:
                    self._ingest_organization_data(item, record_id)
                elif "Child" in item and "Father" in item and "Mother" in item:
                    self._ingest_birth_certificate(item)
                elif "Grantor" in item and "Representative" in item:
                    self._ingest_power_of_attorney(item)
                # Add more dispatchers as needed

        except json.JSONDecodeError:
            # Log error in production
            pass
        except Exception:
            # Log error in production
            pass

    def _ingest_income_data(self, item: Dict[str, Any], record_id: str) -> None:
        """
        Ingest income/tax data.
        Pattern: Person -[:EARNED_INCOME]-> IncomeRecord -[:PAID_BY]-> Organization
        """
        rnokpp = item.get("RNOKPP")
        if not rnokpp:
            return

        # Merge person (basic identity from this record)
        person = Person(
            rnokpp=rnokpp,
            last_name=item.get("last_name", ""),
            first_name=item.get("first_name", ""),
            middle_name=item.get("middle_name"),
            date_birth=item.get("date_birth"),
        )
        self.registry.merge_person(person)

        # Process income sources
        sources = item.get("SourcesOfIncome", [])
        for source in sources:
            tax_agent_code = source.get("TaxAgent")
            tax_agent_name = source.get("NameTaxAgent")

            if not tax_agent_code:
                continue

            # Merge organization (tax agent)
            org = Organization(
                edrpou=tax_agent_code,
                name=tax_agent_name or "Unknown",
            )
            self.registry.merge_organization(org)

            # Process each income record
            income_taxes = source.get("IncomeTaxes", [])
            # Handle both list and dict formats
            if isinstance(income_taxes, dict):
                income_taxes = [income_taxes]

            for income_tax in income_taxes:
                income_record = self._create_income_record(
                    rnokpp=rnokpp,
                    tax_agent_code=tax_agent_code,
                    income_data=income_tax,
                )
                self.registry.merge_income_record(income_record)

                # Create relationships
                self.mutation.link_person_earned_income(rnokpp, income_record.income_id)
                self.mutation.link_income_paid_by_organization(income_record.income_id, tax_agent_code)

    def _ingest_request_data(self, item: Dict[str, Any], record_id: str) -> None:
        """
        Ingest investigation request data.
        Pattern: Executor -[:CREATED_REQUEST]-> Request -[:SUBJECT_OF]-> Person
        """
        person_data = item.get("person", {})
        executor_data = item.get("ExecutorInfo", {})
        period_data = item.get("period", {})

        # Merge subject person
        rnokpp = person_data.get("RNOKPP")
        if rnokpp:
            person = Person(
                rnokpp=rnokpp,
                last_name=person_data.get("last_name", ""),
                first_name=person_data.get("first_name", ""),
                middle_name=person_data.get("middle_name"),
                date_birth=person_data.get("date_birth"),
            )
            self.registry.merge_person(person)

        # Merge executor
        executor_rnokpp = executor_data.get("ExecutorRNOKPP")
        if executor_rnokpp:
            executor = Executor(
                executor_rnokpp=executor_rnokpp,
                executor_edrpou=executor_data.get("ExecutorEDRPOUcode"),
                full_name=executor_data.get("ExecutorFullName", ""),
            )
            self.registry.merge_executor(executor)

        # Merge request
        request_id = item.get("IDrequest", record_id)
        request = Request(
            request_id=request_id,
            basis_request=item.get("basis_request"),
            application_number=item.get("applicationNumber"),
            application_date=item.get("applicationDate"),
            period_begin_month=period_data.get("period_begin_month"),
            period_begin_year=period_data.get("period_begin_year"),
            period_end_month=period_data.get("period_end_month"),
            period_end_year=period_data.get("period_end_year"),
        )
        self.registry.merge_request(request)

        # Create relationships
        if executor_rnokpp and request_id:
            self.mutation.link_executor_created_request(executor_rnokpp, request_id)
        if request_id and rnokpp:
            self.mutation.link_request_subject_of_person(request_id, rnokpp)

    def _ingest_organization_data(self, item: Dict[str, Any], record_id: str) -> None:
        """
        Ingest organization (company) registry data.
        Pattern: Person -[:DIRECTOR_OF|FOUNDER_OF]-> Organization
        """
        code = item.get("code")
        if not code:
            return

        # Merge organization
        names = item.get("names", [])
        primary_name = names[0].get("name") if names else "Unknown"
        short_name = names[0].get("short") if names else None

        org = Organization(
            edrpou=code,
            name=primary_name,
            short_name=short_name,
            state=item.get("state"),
            state_text=item.get("state_text"),
            olf_code=item.get("olf_code"),
            olf_name=item.get("olf_name"),
            authorised_capital=self._parse_float(item.get("authorised_capital", {}).get("value")),
            registration_date=item.get("registration", {}).get("date"),
        )
        self.registry.merge_organization(org)

        # Process founders
        founders = item.get("founders", [])
        for founder in founders:
            founder_code = founder.get("code")
            founder_name = founder.get("name", "")

            if not founder_code or not founder_code.isdigit():
                continue  # Skip non-person founders (foreign companies, etc.)

            # Create person from founder data
            person = self._parse_person_from_name(founder_name, founder_code)
            self.registry.merge_person(person)

            # Create founder relationship
            capital = self._parse_float(founder.get("capital"))
            role_text = founder.get("role_text")
            self.mutation.link_person_founder_of_organization(
                person.rnokpp,
                code,
                capital=capital,
                role_text=role_text,
            )

        # Process directors/heads
        heads = item.get("heads", [])
        for head in heads:
            head_rnokpp = head.get("rnokpp")
            if not head_rnokpp:
                continue

            # Create person from head data
            person = Person(
                rnokpp=head_rnokpp,
                last_name=head.get("last_name", ""),
                first_name=head.get("first_middle_name", "").split()[0] if head.get("first_middle_name") else "",
                middle_name=" ".join(head.get("first_middle_name", "").split()[1:]) if head.get("first_middle_name") else None,
            )
            self.registry.merge_person(person)

            # Create director relationship
            role_text = head.get("role_text")
            self.mutation.link_person_director_of_organization(
                head_rnokpp,
                code,
                role_text=role_text,
            )

    def _ingest_birth_certificate(self, item: Dict[str, Any]) -> None:
        """
        Ingest birth certificate data (family relationships).
        Pattern: Child -[:CHILD_OF]-> Parent
        """
        child_data = item.get("Child", {})
        father_data = item.get("Father", {})
        mother_data = item.get("Mother", {})

        # We need RNOKPP to create persons, but birth certificates may not have it
        # In real system, we'd match by name+birthdate and create synthetic IDs
        # For now, skip if no RNOKPP available
        pass

    def _ingest_power_of_attorney(self, item: Dict[str, Any]) -> None:
        """
        Ingest power of attorney data.
        Pattern: Grantor -[:GRANTOR_OF]-> PoA <-[:REPRESENTATIVE_OF]- Representative
        Pattern: PoA -[:AUTHORIZES_PROPERTY]-> Property
        """
        grantor_data = item.get("Grantor", {})
        representative_data = item.get("Representative", {})
        poa_data = item.get("Power_of_Attorney", {})
        properties = item.get("Properties", [])

        grantor_code = grantor_data.get("Code")
        representative_code = representative_data.get("Code")

        if not grantor_code or not representative_code:
            return

        # Merge persons
        grantor = self._parse_person_from_name(grantor_data.get("Name", ""), grantor_code)
        self.registry.merge_person(grantor)

        representative = self._parse_person_from_name(representative_data.get("Name", ""), representative_code)
        self.registry.merge_person(representative)

        # Merge PoA
        poa_id = self._generate_poa_id(poa_data)
        poa = PowerOfAttorney(
            poa_id=poa_id,
            notarial_reg_number=poa_data.get("Notarial_acts_reg_number"),
            attested_date=poa_data.get("Attested_data"),
            finished_date=poa_data.get("Finished_date"),
            witness_name=poa_data.get("Witness_name"),
        )
        self.registry.merge_power_of_attorney(poa)

        # Create relationships
        self.mutation.link_person_grantor_of_poa(grantor_code, poa_id)
        self.mutation.link_person_representative_of_poa(representative_code, poa_id)

        # Process properties
        for prop_data in properties:
            prop_id = self._generate_property_id(prop_data)
            prop_type = self._determine_property_type(prop_data)

            property_obj = Property(
                property_id=prop_id,
                property_type=prop_type,
                description=prop_data.get("Description", ""),
                government_reg_number=prop_data.get("Government_registration_number"),
                serial_number=prop_data.get("Serial_number"),
            )
            self.registry.merge_property(property_obj)

            # Link property to grantor (ownership)
            self.mutation.link_person_owns_property(grantor_code, prop_id)

            # Link property to PoA
            self.mutation.link_poa_authorizes_property(poa_id, prop_id)

    # ========================================================================
    # Helper methods (ID generation, parsing, etc.)
    # ========================================================================

    def _create_income_record(
        self,
        rnokpp: str,
        tax_agent_code: str,
        income_data: Dict[str, Any],
    ) -> IncomeRecord:
        """
        Create IncomeRecord with synthetic ID.
        WHY: Income records don't have natural keys in source data.
        ID = hash(person + agent + period + type) ensures uniqueness.
        """
        period_quarter_month = str(income_data.get("period_quarter_month", ""))
        period_year = int(income_data.get("period_year", 0))
        income_type_code = str(income_data.get("SignOfIncomePrivilege", "")).split()[0]

        # Generate synthetic ID
        income_id = self._generate_income_id(
            rnokpp, tax_agent_code, period_quarter_month, period_year, income_type_code
        )

        # Parse income type description
        income_type_description = str(income_data.get("SignOfIncomePrivilege", ""))

        return IncomeRecord(
            income_id=income_id,
            income_accrued=self._parse_float(income_data.get("IncomeAccrued", 0)),
            income_paid=self._parse_float(income_data.get("IncomePaid", 0)),
            tax_charged=self._parse_float(income_data.get("TaxCharged", 0)),
            tax_transferred=self._parse_float(income_data.get("TaxTransferred", 0)),
            income_type_code=income_type_code,
            income_type_description=income_type_description,
            period_quarter_month=period_quarter_month,
            period_year=period_year,
            result_income=int(income_data.get("result_income", 1)),
        )

    def _generate_income_id(
        self,
        rnokpp: str,
        tax_agent_code: str,
        period: str,
        year: int,
        income_type: str,
    ) -> str:
        """Generate stable synthetic ID for income record."""
        content = f"{rnokpp}|{tax_agent_code}|{period}|{year}|{income_type}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _generate_property_id(self, prop_data: Dict[str, Any]) -> str:
        """Generate stable synthetic ID for property."""
        content = json.dumps(prop_data, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _generate_poa_id(self, poa_data: Dict[str, Any]) -> str:
        """Generate stable synthetic ID for power of attorney."""
        content = json.dumps(poa_data, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _determine_property_type(self, prop_data: Dict[str, Any]) -> PropertyType:
        """Determine property type from data."""
        vht_id = str(prop_data.get("Vht_id", "")).lower()
        if "автомобіль" in vht_id or "vehicle" in vht_id.lower():
            return PropertyType.VEHICLE
        else:
            return PropertyType.REAL_ESTATE

    def _parse_person_from_name(self, full_name: str, rnokpp: str) -> Person:
        """
        Parse person from full name string (Ukrainian format: ПРІЗВИЩЕ ІМ'Я ПО-БАТЬКОВІ).
        WHY: Source data often has names as single string.
        """
        parts = full_name.strip().split()
        last_name = parts[0] if len(parts) > 0 else ""
        first_name = parts[1] if len(parts) > 1 else ""
        middle_name = parts[2] if len(parts) > 2 else None

        return Person(
            rnokpp=rnokpp,
            last_name=last_name,
            first_name=first_name,
            middle_name=middle_name,
        )

    def _parse_float(self, value: Any) -> Optional[float]:
        """Safely parse float from various input types."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
