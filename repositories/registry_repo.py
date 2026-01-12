from __future__ import annotations

from neo4j import Driver

from core.neo4j_driver import get_driver, get_db_name
from domain.models import Person, Company, Asset
from domain.enums import AssetType


class RegistryRepository:
    """
    Identity layer:
    - MERGE nodes by their stable IDs
    - optionally set/update attributes
    - create constraints/indexes
    """

    def __init__(self, driver: Driver | None = None):
        self._driver = driver or get_driver()
        self._db = get_db_name()

    def ensure_constraints(self) -> None:
        """
        Run once on startup (idempotent).
        Neo4j 5+: CREATE CONSTRAINT ... IF NOT EXISTS
        """
        cypher_statements = [
            # Uniqueness constraints
            """
            CREATE CONSTRAINT person_id_unique IF NOT EXISTS
            FOR (p:Person)
            REQUIRE p.person_id IS UNIQUE
            """,
            """
            CREATE CONSTRAINT company_id_unique IF NOT EXISTS
            FOR (c:Company)
            REQUIRE c.company_id IS UNIQUE
            """,
            """
            CREATE CONSTRAINT asset_id_unique IF NOT EXISTS
            FOR (a:Asset)
            REQUIRE a.asset_id IS UNIQUE
            """,
            # Helpful indexes (optional)
            """
            CREATE INDEX person_name_idx IF NOT EXISTS
            FOR (p:Person)
            ON (p.name)
            """,
            """
            CREATE INDEX company_name_idx IF NOT EXISTS
            FOR (c:Company)
            ON (c.name)
            """,
        ]

        def _tx(tx):
            for stmt in cypher_statements:
                tx.run(stmt)

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def merge_person(self, person: Person) -> None:
        def _tx(tx):
            tx.run(
                """
                MERGE (p:Person {person_id: $person_id})
                SET p.name = $name
                SET p.birth_date = $birth_date
                """,
                person_id=person.person_id,
                name=person.name,
                birth_date=person.birth_date,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def merge_company(self, company: Company) -> None:
        def _tx(tx):
            tx.run(
                """
                MERGE (c:Company {company_id: $company_id})
                SET c.name = $name
                SET c.edrpou = $edrpou
                """,
                company_id=company.company_id,
                name=company.name,
                edrpou=company.edrpou,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def merge_asset(self, asset: Asset) -> None:
        def _tx(tx):
            tx.run(
                """
                MERGE (a:Asset {asset_id: $asset_id})
                SET a.asset_type = $asset_type
                SET a.value = $value
                SET a.description = $description
                """,
                asset_id=asset.asset_id,
                asset_type=str(asset.asset_type.value),
                value=asset.value,
                description=asset.description,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)
