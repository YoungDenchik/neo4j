from __future__ import annotations

from typing import List

from neo4j import Driver

from core.neo4j_driver import get_driver, get_db_name
from domain.models import Asset
from domain.enums import AssetType


class TraversalRepository:
    """
    Traversal layer:
    - multi-hop queries
    - pattern matching
    """

    def __init__(self, driver: Driver | None = None):
        self._driver = driver or get_driver()
        self._db = get_db_name()

    def find_indirect_assets_via_companies(self, person_id: str) -> List[Asset]:
        """
        Person -> (DIRECTOR_OF|OWNER_OF) -> Company -> OWNS -> Asset
        """
        def _tx(tx):
            res = tx.run(
                """
                MATCH (p:Person {person_id: $pid})-[:DIRECTOR_OF|OWNER_OF]->(c:Company)-[:OWNS]->(a:Asset)
                RETURN DISTINCT
                  a.asset_id AS asset_id,
                  a.asset_type AS asset_type,
                  a.value AS value,
                  a.description AS description
                """,
                pid=person_id,
            )
            return [r.data() for r in res]

        with self._driver.session(database=self._db) as session:
            rows = session.execute_read(_tx)

        assets: List[Asset] = []
        for r in rows:
            at = r.get("asset_type") or "OTHER"
            try:
                asset_type = AssetType(at)
            except Exception:
                asset_type = AssetType.OTHER
            assets.append(
                Asset(
                    asset_id=r["asset_id"],
                    asset_type=asset_type,
                    value=r.get("value"),
                    description=r.get("description"),
                )
            )
        return assets
