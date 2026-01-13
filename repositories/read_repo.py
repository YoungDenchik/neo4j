from __future__ import annotations

from typing import List, Optional
from neo4j import Driver

from core.neo4j_driver import get_driver, get_db_name
from domain.models import Person, Organization, IncomeRecord, Property, Request
from domain.enums import PropertyType


class ReadRepository:
    """
    Read layer (single-node queries and simple aggregations).

    RESPONSIBILITIES:
    - Fetch individual entities by ID
    - Simple aggregations (count, sum) on single node type
    - NO complex graph traversals (use TraversalRepository for that)
    - NO business logic (that belongs in services)

    WHY: Separates simple reads from complex graph queries.
    Optimized for execute_read transactions (read-only).

    DESIGN PRINCIPLE: This repository returns domain models (dataclasses),
    not raw Neo4j records. Services work with domain objects, not database primitives.
    """

    def __init__(self, driver: Driver | None = None):
        self._driver = driver or get_driver()
        self._db = get_db_name()

    # ========================================================================
    # Person queries
    # ========================================================================

    def get_person_by_rnokpp(self, rnokpp: str) -> Optional[Person]:
        """
        Fetch person by unique RNOKPP.
        Returns None if not found.
        """
        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person {rnokpp: $rnokpp})
                RETURN p.rnokpp as rnokpp,
                       p.last_name as last_name,
                       p.first_name as first_name,
                       p.middle_name as middle_name,
                       p.date_birth as date_birth
                """,
                rnokpp=rnokpp,
            )
            record = result.single()
            if record is None:
                return None

            return Person(
                rnokpp=record["rnokpp"],
                last_name=record["last_name"],
                first_name=record["first_name"],
                middle_name=record["middle_name"],
                date_birth=record["date_birth"],
            )

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    def search_persons_by_name(
        self,
        last_name: Optional[str] = None,
        first_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Person]:
        """
        Search persons by name (case-insensitive partial match).
        WHY: Common UI requirement for name-based search.
        """
        def _tx(tx):
            # Build dynamic query based on provided parameters
            conditions = []
            params = {"limit": limit}

            if last_name:
                conditions.append("p.last_name CONTAINS $last_name")
                params["last_name"] = last_name

            if first_name:
                conditions.append("p.first_name CONTAINS $first_name")
                params["first_name"] = first_name

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

            result = tx.run(
                f"""
                MATCH (p:Person)
                {where_clause}
                RETURN p.rnokpp as rnokpp,
                       p.last_name as last_name,
                       p.first_name as first_name,
                       p.middle_name as middle_name,
                       p.date_birth as date_birth
                LIMIT $limit
                """,
                **params,
            )

            persons = []
            for record in result:
                persons.append(
                    Person(
                        rnokpp=record["rnokpp"],
                        last_name=record["last_name"],
                        first_name=record["first_name"],
                        middle_name=record["middle_name"],
                        date_birth=record["date_birth"],
                    )
                )
            return persons

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    # ========================================================================
    # Organization queries
    # ========================================================================

    def get_organization_by_edrpou(self, edrpou: str) -> Optional[Organization]:
        """
        Fetch organization by unique EDRPOU.
        Returns None if not found.
        """
        def _tx(tx):
            result = tx.run(
                """
                MATCH (o:Organization {edrpou: $edrpou})
                RETURN o.edrpou as edrpou,
                       o.name as name,
                       o.short_name as short_name,
                       o.state as state,
                       o.state_text as state_text,
                       o.olf_code as olf_code,
                       o.olf_name as olf_name,
                       o.authorised_capital as authorised_capital,
                       o.registration_date as registration_date
                """,
                edrpou=edrpou,
            )
            record = result.single()
            if record is None:
                return None

            return Organization(
                edrpou=record["edrpou"],
                name=record["name"],
                short_name=record["short_name"],
                state=record["state"],
                state_text=record["state_text"],
                olf_code=record["olf_code"],
                olf_name=record["olf_name"],
                authorised_capital=record["authorised_capital"],
                registration_date=record["registration_date"],
            )

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    def search_organizations_by_name(
        self,
        name: str,
        limit: int = 100,
    ) -> List[Organization]:
        """
        Search organizations by name (case-insensitive partial match).
        WHY: Common UI requirement for company name search.
        """
        def _tx(tx):
            result = tx.run(
                """
                MATCH (o:Organization)
                WHERE o.name CONTAINS $name
                RETURN o.edrpou as edrpou,
                       o.name as name,
                       o.short_name as short_name,
                       o.state as state,
                       o.state_text as state_text,
                       o.olf_code as olf_code,
                       o.olf_name as olf_name,
                       o.authorised_capital as authorised_capital,
                       o.registration_date as registration_date
                LIMIT $limit
                """,
                name=name,
                limit=limit,
            )

            orgs = []
            for record in result:
                orgs.append(
                    Organization(
                        edrpou=record["edrpou"],
                        name=record["name"],
                        short_name=record["short_name"],
                        state=record["state"],
                        state_text=record["state_text"],
                        olf_code=record["olf_code"],
                        olf_name=record["olf_name"],
                        authorised_capital=record["authorised_capital"],
                        registration_date=record["registration_date"],
                    )
                )
            return orgs

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    # ========================================================================
    # IncomeRecord queries
    # ========================================================================

    def get_income_records_for_person(
        self,
        rnokpp: str,
        year: Optional[int] = None,
    ) -> List[IncomeRecord]:
        """
        Fetch all income records for a person.
        Optionally filter by year.
        WHY: Common query for income analysis.
        """
        def _tx(tx):
            year_filter = "AND i.period_year = $year" if year else ""

            result = tx.run(
                f"""
                MATCH (p:Person {{rnokpp: $rnokpp}})-[:EARNED_INCOME]->(i:IncomeRecord)
                WHERE true {year_filter}
                RETURN i.income_id as income_id,
                       i.income_accrued as income_accrued,
                       i.income_paid as income_paid,
                       i.tax_charged as tax_charged,
                       i.tax_transferred as tax_transferred,
                       i.income_type_code as income_type_code,
                       i.income_type_description as income_type_description,
                       i.period_quarter_month as period_quarter_month,
                       i.period_year as period_year,
                       i.result_income as result_income
                ORDER BY i.period_year DESC, i.period_quarter_month
                """,
                rnokpp=rnokpp,
                year=year,
            )

            records = []
            for record in result:
                records.append(
                    IncomeRecord(
                        income_id=record["income_id"],
                        income_accrued=record["income_accrued"],
                        income_paid=record["income_paid"],
                        tax_charged=record["tax_charged"],
                        tax_transferred=record["tax_transferred"],
                        income_type_code=record["income_type_code"],
                        income_type_description=record["income_type_description"],
                        period_quarter_month=record["period_quarter_month"],
                        period_year=record["period_year"],
                        result_income=record["result_income"],
                    )
                )
            return records

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    # ========================================================================
    # Property queries
    # ========================================================================

    def get_properties_owned_by_person(self, rnokpp: str) -> List[Property]:
        """
        Fetch all properties directly owned by person.
        WHY: Asset disclosure for AML analysis.
        """
        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person {rnokpp: $rnokpp})-[:OWNS]->(prop:Property)
                RETURN prop.property_id as property_id,
                       prop.property_type as property_type,
                       prop.description as description,
                       prop.government_reg_number as government_reg_number,
                       prop.serial_number as serial_number,
                       prop.address as address,
                       prop.area as area
                """,
                rnokpp=rnokpp,
            )

            properties = []
            for record in result:
                properties.append(
                    Property(
                        property_id=record["property_id"],
                        property_type=PropertyType(record["property_type"]),
                        description=record["description"],
                        government_reg_number=record["government_reg_number"],
                        serial_number=record["serial_number"],
                        address=record["address"],
                        area=record["area"],
                    )
                )
            return properties

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    # ========================================================================
    # Simple aggregations
    # ========================================================================

    def count_nodes_by_label(self, label: str) -> int:
        """
        Count total nodes of a given label.
        WHY: For monitoring data ingestion and database statistics.
        """
        def _tx(tx):
            result = tx.run(
                f"MATCH (n:{label}) RETURN count(n) as count"
            )
            record = result.single()
            return record["count"] if record else 0

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    def get_total_income_for_person(self, rnokpp: str) -> float:
        """
        Calculate total income paid to person across all records.
        WHY: Quick financial summary.
        """
        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person {rnokpp: $rnokpp})-[:EARNED_INCOME]->(i:IncomeRecord)
                RETURN sum(i.income_paid) as total
                """,
                rnokpp=rnokpp,
            )
            record = result.single()
            return record["total"] if record and record["total"] else 0.0

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)
