from __future__ import annotations

from typing import List

from neo4j import Driver

from core.neo4j_driver import get_driver, get_db_name
from domain.models import Person, Company, Asset, PersonProfile
from domain.enums import AssetType


class ReadRepository:
    """
    Read layer:
    - returns computed views (aggregates/subgraphs)
    - does not mutate graph
    """

    def __init__(self, driver: Driver | None = None):
        self._driver = driver or get_driver()
        self._db = get_db_name()

    def load_person_profile(self, person_id: str) -> PersonProfile | None:
        """
        Minimal profile:
        - Person node
        - direct assets: (Person)-[:OWNS]->(Asset)
        - companies: (Person)-[:DIRECTOR_OF|OWNER_OF]->(Company)
        """

        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person {person_id: $pid})

                OPTIONAL MATCH (p)-[:OWNS]->(ad:Asset)

                OPTIONAL MATCH (p)-[:DIRECTOR_OF|OWNER_OF]->(c:Company)

                RETURN
                  p.person_id AS pid,
                  p.name AS pname,
                  p.birth_date AS birth_date,
                  collect(DISTINCT {
                    asset_id: ad.asset_id,
                    asset_type: ad.asset_type,
                    value: ad.value,
                    description: ad.description
                  }) AS direct_assets,
                  collect(DISTINCT {
                    company_id: c.company_id,
                    name: c.name,
                    edrpou: c.edrpou
                  }) AS companies
                """,
                pid=person_id,
            )
            rec = result.single()
            if not rec:
                return None
            return rec.data()

        with self._driver.session(database=self._db) as session:
            data = session.execute_read(_tx)

        if data is None:
            return None

        person = Person(
            person_id=data["pid"],
            name=data["pname"],
            birth_date=data.get("birth_date"),
        )

        companies: List[Company] = []
        for c in data.get("companies", []):
            if c.get("company_id") is None:
                continue
            companies.append(Company(company_id=c["company_id"], name=c.get("name") or "", edrpou=c.get("edrpou")))

        assets_direct: List[Asset] = []
        for a in data.get("direct_assets", []):
            if a.get("asset_id") is None:
                continue
            at = a.get("asset_type") or "OTHER"
            try:
                asset_type = AssetType(at)
            except Exception:
                asset_type = AssetType.OTHER
            assets_direct.append(
                Asset(
                    asset_id=a["asset_id"],
                    asset_type=asset_type,
                    value=a.get("value"),
                    description=a.get("description"),
                )
            )

        return PersonProfile(person=person, companies=companies, assets_direct=assets_direct)
