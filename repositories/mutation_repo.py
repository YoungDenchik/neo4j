from __future__ import annotations

from neo4j import Driver

from core.neo4j_driver import get_driver, get_db_name
from domain.enums import RelType


class GraphMutationRepository:
    """
    Graph mutation layer:
    - only creates/merges relationships between existing nodes
    - no business logic, no analytics
    """

    def __init__(self, driver: Driver | None = None):
        self._driver = driver or get_driver()
        self._db = get_db_name()

    def link_person_owns_asset(self, person_id: str, asset_id: str, since_year: int | None = None) -> None:
        def _tx(tx):
            tx.run(
                f"""
                MATCH (p:Person {{person_id: $pid}})
                MATCH (a:Asset  {{asset_id:  $aid}})
                MERGE (p)-[r:{RelType.OWNS.value}]->(a)
                SET r.since_year = coalesce(r.since_year, $since_year)
                """,
                pid=person_id,
                aid=asset_id,
                since_year=since_year,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def link_person_director_of_company(self, person_id: str, company_id: str) -> None:
        def _tx(tx):
            tx.run(
                f"""
                MATCH (p:Person  {{person_id:  $pid}})
                MATCH (c:Company {{company_id: $cid}})
                MERGE (p)-[:{RelType.DIRECTOR_OF.value}]->(c)
                """,
                pid=person_id,
                cid=company_id,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def link_person_owner_of_company(self, person_id: str, company_id: str, share: float | None = None) -> None:
        def _tx(tx):
            tx.run(
                f"""
                MATCH (p:Person  {{person_id:  $pid}})
                MATCH (c:Company {{company_id: $cid}})
                MERGE (p)-[r:{RelType.OWNER_OF.value}]->(c)
                SET r.share = $share
                """,
                pid=person_id,
                cid=company_id,
                share=share,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def link_company_owns_asset(self, company_id: str, asset_id: str) -> None:
        def _tx(tx):
            tx.run(
                f"""
                MATCH (c:Company {{company_id: $cid}})
                MATCH (a:Asset   {{asset_id:  $aid}})
                MERGE (c)-[:{RelType.COMPANY_OWNS.value}]->(a)
                """,
                cid=company_id,
                aid=asset_id,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)
