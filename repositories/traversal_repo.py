from __future__ import annotations

from typing import List, Dict, Any
from neo4j import Driver

from core.neo4j_driver import get_driver, get_db_name
from domain.models import Person, Organization, Property, IncomeAggregate
from domain.enums import PropertyType


class TraversalRepository:
    """
    Traversal layer (multi-hop graph queries and pattern matching).

    RESPONSIBILITIES:
    - Complex graph traversals (2+ hops)
    - Pattern matching for AML/KYC investigations
    - Graph algorithms (shortest path, connected components, etc.)
    - NO business logic (that belongs in services)

    WHY: Separates complex graph queries from simple reads.
    These queries are optimized for graph relationships, not single nodes.

    DESIGN PRINCIPLE: Returns computed data (aggregates, paths, networks),
    not just single entities. Often returns dict/list structures that
    services transform into domain models.
    """

    def __init__(self, driver: Driver | None = None):
        self._driver = driver or get_driver()
        self._db = get_db_name()

    # ========================================================================
    # Corporate network traversals
    # ========================================================================

    def get_directors_for_organization(self, edrpou: str) -> List[Person]:
        """
        Find all directors of an organization.
        WHY: Corporate governance - who controls the company?
        """
        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person)-[:DIRECTOR_OF]->(o:Organization {edrpou: $edrpou})
                RETURN p.rnokpp as rnokpp,
                       p.last_name as last_name,
                       p.first_name as first_name,
                       p.middle_name as middle_name,
                       p.date_birth as date_birth
                """,
                edrpou=edrpou,
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

    def get_founders_for_organization(self, edrpou: str) -> List[Dict[str, Any]]:
        """
        Find all founders/shareholders of an organization with their capital stakes.
        WHY: Beneficial ownership - who owns the company?
        Returns list of dicts with person and capital info.
        """
        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person)-[r:FOUNDER_OF]->(o:Organization {edrpou: $edrpou})
                RETURN p.rnokpp as rnokpp,
                       p.last_name as last_name,
                       p.first_name as first_name,
                       p.middle_name as middle_name,
                       p.date_birth as date_birth,
                       r.capital as capital,
                       r.role_text as role_text
                """,
                edrpou=edrpou,
            )

            founders = []
            for record in result:
                founders.append({
                    "person": Person(
                        rnokpp=record["rnokpp"],
                        last_name=record["last_name"],
                        first_name=record["first_name"],
                        middle_name=record["middle_name"],
                        date_birth=record["date_birth"],
                    ),
                    "capital": record["capital"],
                    "role_text": record["role_text"],
                })
            return founders

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    def get_organizations_controlled_by_person(self, rnokpp: str) -> Dict[str, List[Organization]]:
        """
        Find all organizations where person has a role (director or founder).
        WHY: Control structure - what companies does this person influence?
        Returns dict with 'director_of' and 'founder_of' lists.
        """
        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person {rnokpp: $rnokpp})
                OPTIONAL MATCH (p)-[:DIRECTOR_OF]->(o_dir:Organization)
                OPTIONAL MATCH (p)-[:FOUNDER_OF]->(o_founder:Organization)
                RETURN
                    collect(DISTINCT {
                        edrpou: o_dir.edrpou,
                        name: o_dir.name,
                        short_name: o_dir.short_name,
                        state: o_dir.state,
                        state_text: o_dir.state_text,
                        olf_code: o_dir.olf_code,
                        olf_name: o_dir.olf_name,
                        authorised_capital: o_dir.authorised_capital,
                        registration_date: o_dir.registration_date
                    }) as director_of,
                    collect(DISTINCT {
                        edrpou: o_founder.edrpou,
                        name: o_founder.name,
                        short_name: o_founder.short_name,
                        state: o_founder.state,
                        state_text: o_founder.state_text,
                        olf_code: o_founder.olf_code,
                        olf_name: o_founder.olf_name,
                        authorised_capital: o_founder.authorised_capital,
                        registration_date: o_founder.registration_date
                    }) as founder_of
                """,
                rnokpp=rnokpp,
            )

            record = result.single()
            if not record:
                return {"director_of": [], "founder_of": []}

            director_of = []
            for org_data in record["director_of"]:
                if org_data["edrpou"] is not None:
                    director_of.append(Organization(**org_data))

            founder_of = []
            for org_data in record["founder_of"]:
                if org_data["edrpou"] is not None:
                    founder_of.append(Organization(**org_data))

            return {"director_of": director_of, "founder_of": founder_of}

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    # ========================================================================
    # Income network traversals
    # ========================================================================

    def get_income_by_tax_agent(self, rnokpp: str) -> List[IncomeAggregate]:
        """
        Aggregate income by tax agent (employer).
        WHY: Income source analysis - where does the person's money come from?
        Returns list of IncomeAggregate objects.
        """
        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person {rnokpp: $rnokpp})-[:EARNED_INCOME]->(i:IncomeRecord)-[:PAID_BY]->(o:Organization)
                WITH o, i
                RETURN
                    o.edrpou as edrpou,
                    o.name as name,
                    sum(i.income_accrued) as total_accrued,
                    sum(i.income_paid) as total_paid,
                    sum(i.tax_charged) as total_tax_charged,
                    sum(i.tax_transferred) as total_tax_transferred,
                    collect(DISTINCT i.period_year) as years,
                    count(i) as record_count,
                    max(CASE WHEN i.income_accrued <> i.income_paid THEN true ELSE false END) as has_unpaid_income,
                    max(CASE WHEN i.tax_charged <> i.tax_transferred THEN true ELSE false END) as has_unpaid_tax
                ORDER BY total_paid DESC
                """,
                rnokpp=rnokpp,
            )

            aggregates = []
            for record in result:
                aggregates.append(
                    IncomeAggregate(
                        person_rnokpp=rnokpp,
                        tax_agent_edrpou=record["edrpou"],
                        tax_agent_name=record["name"],
                        total_accrued=record["total_accrued"] or 0.0,
                        total_paid=record["total_paid"] or 0.0,
                        total_tax_charged=record["total_tax_charged"] or 0.0,
                        total_tax_transferred=record["total_tax_transferred"] or 0.0,
                        years=record["years"] or [],
                        record_count=record["record_count"],
                        has_unpaid_income=record["has_unpaid_income"],
                        has_unpaid_tax=record["has_unpaid_tax"],
                    )
                )
            return aggregates

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    # ========================================================================
    # Family network traversals
    # ========================================================================

    def get_family_network(self, rnokpp: str, depth: int = 2) -> Dict[str, List[Person]]:
        """
        Find family members within N hops (parents, children, spouses).
        WHY: Family network analysis - relatives often share wealth.
        Returns dict with 'children', 'parents', 'spouse', 'extended' lists.
        """
        def _tx(tx):
            result = tx.run(
                f"""
                MATCH (p:Person {{rnokpp: $rnokpp}})

                // Direct children
                OPTIONAL MATCH (p)<-[:CHILD_OF]-(child:Person)

                // Direct parents
                OPTIONAL MATCH (p)-[:CHILD_OF]->(parent:Person)

                // Spouse
                OPTIONAL MATCH (p)-[:SPOUSE_OF]-(spouse:Person)

                // Extended family (up to depth hops)
                OPTIONAL MATCH path = (p)-[:CHILD_OF|SPOUSE_OF*1..{depth}]-(extended:Person)
                WHERE extended.rnokpp <> p.rnokpp
                  AND extended.rnokpp NOT IN [child.rnokpp, parent.rnokpp, spouse.rnokpp]

                RETURN
                    collect(DISTINCT {{
                        rnokpp: child.rnokpp,
                        last_name: child.last_name,
                        first_name: child.first_name,
                        middle_name: child.middle_name,
                        date_birth: child.date_birth
                    }}) as children,
                    collect(DISTINCT {{
                        rnokpp: parent.rnokpp,
                        last_name: parent.last_name,
                        first_name: parent.first_name,
                        middle_name: parent.middle_name,
                        date_birth: parent.date_birth
                    }}) as parents,
                    collect(DISTINCT {{
                        rnokpp: spouse.rnokpp,
                        last_name: spouse.last_name,
                        first_name: spouse.first_name,
                        middle_name: spouse.middle_name,
                        date_birth: spouse.date_birth
                    }}) as spouses,
                    collect(DISTINCT {{
                        rnokpp: extended.rnokpp,
                        last_name: extended.last_name,
                        first_name: extended.first_name,
                        middle_name: extended.middle_name,
                        date_birth: extended.date_birth
                    }}) as extended
                """,
                rnokpp=rnokpp,
            )

            record = result.single()
            if not record:
                return {"children": [], "parents": [], "spouse": None, "extended": []}

            def to_person_list(data_list):
                persons = []
                for item in data_list:
                    if item.get("rnokpp") is not None:
                        persons.append(Person(**item))
                return persons

            children = to_person_list(record["children"])
            parents = to_person_list(record["parents"])
            spouses = to_person_list(record["spouses"])
            spouse = spouses[0] if spouses else None
            extended = to_person_list(record["extended"])

            return {
                "children": children,
                "parents": parents,
                "spouse": spouse,
                "extended": extended,
            }

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    # ========================================================================
    # Property control traversals
    # ========================================================================

    def get_properties_controlled_via_poa(self, rnokpp: str) -> List[Property]:
        """
        Find properties person controls via Power of Attorney (not direct ownership).
        WHY: Hidden control - person may manage assets without owning them.
        Pattern: Person -[:REPRESENTATIVE_OF]-> PoA -[:AUTHORIZES_PROPERTY]-> Property
        """
        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person {rnokpp: $rnokpp})-[:REPRESENTATIVE_OF]->(poa:PowerOfAttorney)-[:AUTHORIZES_PROPERTY]->(prop:Property)
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
    # Investigation traversals
    # ========================================================================

    def get_co_directors(self, rnokpp: str) -> List[Dict[str, Any]]:
        """
        Find people who are co-directors with this person (serve on same boards).
        WHY: Network analysis - who does this person work with?
        Returns list of dicts with person and shared organizations.
        """
        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person {rnokpp: $rnokpp})-[:DIRECTOR_OF]->(o:Organization)<-[:DIRECTOR_OF]-(co_dir:Person)
                WHERE co_dir.rnokpp <> p.rnokpp
                WITH co_dir, collect(DISTINCT o.name) as shared_orgs, count(DISTINCT o) as shared_count
                RETURN
                    co_dir.rnokpp as rnokpp,
                    co_dir.last_name as last_name,
                    co_dir.first_name as first_name,
                    co_dir.middle_name as middle_name,
                    co_dir.date_birth as date_birth,
                    shared_orgs,
                    shared_count
                ORDER BY shared_count DESC
                """,
                rnokpp=rnokpp,
            )

            co_directors = []
            for record in result:
                co_directors.append({
                    "person": Person(
                        rnokpp=record["rnokpp"],
                        last_name=record["last_name"],
                        first_name=record["first_name"],
                        middle_name=record["middle_name"],
                        date_birth=record["date_birth"],
                    ),
                    "shared_organizations": record["shared_orgs"],
                    "shared_count": record["shared_count"],
                })
            return co_directors

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    def find_circular_ownership(self, max_depth: int = 5) -> List[List[str]]:
        """
        Detect circular ownership structures (A owns B owns C owns A).
        WHY: Complex corporate structures may hide beneficial ownership.
        Returns list of circular paths (each path is list of EDRPOUs).
        """
        def _tx(tx):
            result = tx.run(
                f"""
                MATCH path = (o1:Organization)<-[:FOUNDER_OF]-(:Person)-[:FOUNDER_OF]->(o2:Organization)
                WHERE (o2)<-[:FOUNDER_OF*1..{max_depth}]-(:Person)-[:FOUNDER_OF]->(o1)
                RETURN [node in nodes(path) | node.edrpou] as cycle
                LIMIT 100
                """
            )

            cycles = []
            for record in result:
                cycle = [edrpou for edrpou in record["cycle"] if edrpou is not None]
                if cycle:
                    cycles.append(cycle)
            return cycles

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)
