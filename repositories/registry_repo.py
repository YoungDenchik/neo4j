from __future__ import annotations

from neo4j import Driver

from core.neo4j_driver import get_driver, get_db_name
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


class RegistryRepository:
    """
    Identity layer (registry of entities).

    RESPONSIBILITIES:
    - MERGE nodes by their stable unique IDs (ensures no duplicates)
    - Set/update node attributes
    - Create uniqueness constraints and indexes

    WHY: Separates identity management from relationship management.
    MERGE operations are expensive - we do them once here, not scattered across codebase.

    DESIGN PRINCIPLE: Each entity has exactly one stable identifier:
    - Person: rnokpp
    - Organization: edrpou
    - IncomeRecord: income_id (synthetic)
    - Property: property_id (synthetic)
    - Request: request_id
    - Executor: executor_rnokpp
    - PowerOfAttorney: poa_id (synthetic)
    """

    def __init__(self, driver: Driver | None = None):
        self._driver = driver or get_driver()
        self._db = get_db_name()

    def ensure_constraints(self) -> None:
        """
        Create uniqueness constraints and indexes.
        Run once on startup (idempotent).

        WHY: Constraints enforce schema governance at database level.
        Neo4j 5+: CREATE CONSTRAINT ... IF NOT EXISTS
        """
        cypher_statements = [
            # ========== Uniqueness constraints ==========
            """
            CREATE CONSTRAINT person_rnokpp_unique IF NOT EXISTS
            FOR (p:Person)
            REQUIRE p.rnokpp IS UNIQUE
            """,
            """
            CREATE CONSTRAINT org_edrpou_unique IF NOT EXISTS
            FOR (o:Organization)
            REQUIRE o.edrpou IS UNIQUE
            """,
            """
            CREATE CONSTRAINT income_id_unique IF NOT EXISTS
            FOR (i:IncomeRecord)
            REQUIRE i.income_id IS UNIQUE
            """,
            """
            CREATE CONSTRAINT property_id_unique IF NOT EXISTS
            FOR (p:Property)
            REQUIRE p.property_id IS UNIQUE
            """,
            """
            CREATE CONSTRAINT request_id_unique IF NOT EXISTS
            FOR (r:Request)
            REQUIRE r.request_id IS UNIQUE
            """,
            """
            CREATE CONSTRAINT executor_rnokpp_unique IF NOT EXISTS
            FOR (e:Executor)
            REQUIRE e.executor_rnokpp IS UNIQUE
            """,
            """
            CREATE CONSTRAINT poa_id_unique IF NOT EXISTS
            FOR (p:PowerOfAttorney)
            REQUIRE p.poa_id IS UNIQUE
            """,
            # ========== Performance indexes ==========
            # WHY: Speed up common queries (name search, temporal queries)
            """
            CREATE INDEX person_name_idx IF NOT EXISTS
            FOR (p:Person)
            ON (p.last_name, p.first_name)
            """,
            """
            CREATE INDEX person_birth_idx IF NOT EXISTS
            FOR (p:Person)
            ON (p.date_birth)
            """,
            """
            CREATE INDEX org_name_idx IF NOT EXISTS
            FOR (o:Organization)
            ON (o.name)
            """,
            """
            CREATE INDEX org_state_idx IF NOT EXISTS
            FOR (o:Organization)
            ON (o.state)
            """,
            """
            CREATE INDEX income_year_idx IF NOT EXISTS
            FOR (i:IncomeRecord)
            ON (i.period_year)
            """,
            """
            CREATE INDEX income_type_idx IF NOT EXISTS
            FOR (i:IncomeRecord)
            ON (i.income_type_code)
            """,
            """
            CREATE INDEX request_date_idx IF NOT EXISTS
            FOR (r:Request)
            ON (r.application_date)
            """,
        ]

        def _tx(tx):
            for stmt in cypher_statements:
                tx.run(stmt)

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    # ========================================================================
    # MERGE operations (upsert nodes by identity)
    # ========================================================================

    def merge_person(self, person: Person) -> None:
        """
        MERGE person by rnokpp, update attributes.
        WHY: RNOKPP is government-issued stable identifier.
        Names may change (marriage) but RNOKPP does not.
        """
        def _tx(tx):
            tx.run(
                """
                MERGE (p:Person {rnokpp: $rnokpp})
                SET p.last_name = $last_name,
                    p.first_name = $first_name,
                    p.middle_name = $middle_name,
                    p.date_birth = $date_birth
                """,
                rnokpp=person.rnokpp,
                last_name=person.last_name,
                first_name=person.first_name,
                middle_name=person.middle_name,
                date_birth=person.date_birth,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def merge_organization(self, org: Organization) -> None:
        """
        MERGE organization by edrpou, update attributes.
        WHY: EDRPOU is company registration code, stable identifier.
        """
        def _tx(tx):
            tx.run(
                """
                MERGE (o:Organization {edrpou: $edrpou})
                SET o.name = $name,
                    o.short_name = $short_name,
                    o.state = $state,
                    o.state_text = $state_text,
                    o.olf_code = $olf_code,
                    o.olf_name = $olf_name,
                    o.authorised_capital = $authorised_capital,
                    o.registration_date = $registration_date
                """,
                edrpou=org.edrpou,
                name=org.name,
                short_name=org.short_name,
                state=org.state,
                state_text=org.state_text,
                olf_code=org.olf_code,
                olf_name=org.olf_name,
                authorised_capital=org.authorised_capital,
                registration_date=org.registration_date,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def merge_income_record(self, income: IncomeRecord) -> None:
        """
        MERGE income record by synthetic income_id.
        WHY: Each income payment is a distinct fact.
        income_id = hash(person + tax_agent + period + type) ensures uniqueness.
        """
        def _tx(tx):
            tx.run(
                """
                MERGE (i:IncomeRecord {income_id: $income_id})
                SET i.income_accrued = $income_accrued,
                    i.income_paid = $income_paid,
                    i.tax_charged = $tax_charged,
                    i.tax_transferred = $tax_transferred,
                    i.income_type_code = $income_type_code,
                    i.income_type_description = $income_type_description,
                    i.period_quarter_month = $period_quarter_month,
                    i.period_year = $period_year,
                    i.result_income = $result_income
                """,
                income_id=income.income_id,
                income_accrued=income.income_accrued,
                income_paid=income.income_paid,
                tax_charged=income.tax_charged,
                tax_transferred=income.tax_transferred,
                income_type_code=income.income_type_code,
                income_type_description=income.income_type_description,
                period_quarter_month=income.period_quarter_month,
                period_year=income.period_year,
                result_income=income.result_income,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def merge_property(self, prop: Property) -> None:
        """
        MERGE property by synthetic property_id.
        WHY: Properties may not have natural keys in source data.
        Generate stable ID from content hash.
        """
        def _tx(tx):
            tx.run(
                """
                MERGE (p:Property {property_id: $property_id})
                SET p.property_type = $property_type,
                    p.description = $description,
                    p.government_reg_number = $government_reg_number,
                    p.serial_number = $serial_number,
                    p.address = $address,
                    p.area = $area
                """,
                property_id=prop.property_id,
                property_type=prop.property_type.value,
                description=prop.description,
                government_reg_number=prop.government_reg_number,
                serial_number=prop.serial_number,
                address=prop.address,
                area=prop.area,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def merge_request(self, request: Request) -> None:
        """
        MERGE investigation request by request_id.
        WHY: Tracks data provenance - which investigation triggered this data.
        """
        def _tx(tx):
            tx.run(
                """
                MERGE (r:Request {request_id: $request_id})
                SET r.basis_request = $basis_request,
                    r.application_number = $application_number,
                    r.application_date = $application_date,
                    r.period_begin_month = $period_begin_month,
                    r.period_begin_year = $period_begin_year,
                    r.period_end_month = $period_end_month,
                    r.period_end_year = $period_end_year
                """,
                request_id=request.request_id,
                basis_request=request.basis_request,
                application_number=request.application_number,
                application_date=request.application_date,
                period_begin_month=request.period_begin_month,
                period_begin_year=request.period_begin_year,
                period_end_month=request.period_end_month,
                period_end_year=request.period_end_year,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def merge_executor(self, executor: Executor) -> None:
        """
        MERGE executor (investigator) by executor_rnokpp.
        WHY: Separate from Person - executors are investigators, not subjects.
        """
        def _tx(tx):
            tx.run(
                """
                MERGE (e:Executor {executor_rnokpp: $executor_rnokpp})
                SET e.executor_edrpou = $executor_edrpou,
                    e.full_name = $full_name
                """,
                executor_rnokpp=executor.executor_rnokpp,
                executor_edrpou=executor.executor_edrpou,
                full_name=executor.full_name,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def merge_power_of_attorney(self, poa: PowerOfAttorney) -> None:
        """
        MERGE power of attorney document by synthetic poa_id.
        WHY: Shows control relationships - critical for finding beneficial owners.
        """
        def _tx(tx):
            tx.run(
                """
                MERGE (p:PowerOfAttorney {poa_id: $poa_id})
                SET p.notarial_reg_number = $notarial_reg_number,
                    p.attested_date = $attested_date,
                    p.finished_date = $finished_date,
                    p.witness_name = $witness_name
                """,
                poa_id=poa.poa_id,
                notarial_reg_number=poa.notarial_reg_number,
                attested_date=poa.attested_date,
                finished_date=poa.finished_date,
                witness_name=poa.witness_name,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)
