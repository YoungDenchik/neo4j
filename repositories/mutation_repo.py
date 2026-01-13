from __future__ import annotations

from neo4j import Driver

from core.neo4j_driver import get_driver, get_db_name
from domain.enums import RelType


class GraphMutationRepository:
    """
    Graph mutation layer (relationship creation).

    RESPONSIBILITIES:
    - Create/merge relationships between existing nodes
    - Set relationship properties
    - NO business logic, NO analytics, NO queries

    WHY: Separates fact creation from identity management and reads.
    All relationships represent exactly one fact or action.

    DESIGN PRINCIPLE: Relationships are IMMUTABLE facts.
    - Use MERGE for symmetric relationships (SPOUSE_OF)
    - Use CREATE for temporal facts (income payments, corporate roles)
    - Properties on relationships store contextual data (amounts, dates)

    IMPORTANT: This repository assumes nodes already exist (via RegistryRepository).
    If nodes don't exist, relationships will not be created (MATCH will fail).
    """

    def __init__(self, driver: Driver | None = None):
        self._driver = driver or get_driver()
        self._db = get_db_name()

    # ========================================================================
    # Person → Organization relationships
    # ========================================================================

    def link_person_director_of_organization(
        self,
        person_rnokpp: str,
        org_edrpou: str,
        role_text: str | None = None,
    ) -> None:
        """
        Create DIRECTOR_OF relationship.
        WHY: Director is a legal role - person has authority over organization.
        """
        def _tx(tx):
            tx.run(
                f"""
                MATCH (p:Person {{rnokpp: $person_rnokpp}})
                MATCH (o:Organization {{edrpou: $org_edrpou}})
                MERGE (p)-[r:{RelType.DIRECTOR_OF.value}]->(o)
                SET r.role_text = $role_text
                """,
                person_rnokpp=person_rnokpp,
                org_edrpou=org_edrpou,
                role_text=role_text,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def link_person_founder_of_organization(
        self,
        person_rnokpp: str,
        org_edrpou: str,
        capital: float | None = None,
        role_text: str | None = None,
    ) -> None:
        """
        Create FOUNDER_OF relationship.
        WHY: Founder/shareholder has ownership stake - critical for beneficial ownership.
        """
        def _tx(tx):
            tx.run(
                f"""
                MATCH (p:Person {{rnokpp: $person_rnokpp}})
                MATCH (o:Organization {{edrpou: $org_edrpou}})
                MERGE (p)-[r:{RelType.FOUNDER_OF.value}]->(o)
                SET r.capital = $capital,
                    r.role_text = $role_text
                """,
                person_rnokpp=person_rnokpp,
                org_edrpou=org_edrpou,
                capital=capital,
                role_text=role_text,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    # ========================================================================
    # Person → Person relationships (family)
    # ========================================================================

    def link_person_child_of_person(
        self,
        child_rnokpp: str,
        parent_rnokpp: str,
    ) -> None:
        """
        Create CHILD_OF relationship.
        WHY: Family relationships are critical for AML - relatives often control assets.
        Direction: child → parent (clear semantics).
        """
        def _tx(tx):
            tx.run(
                f"""
                MATCH (child:Person {{rnokpp: $child_rnokpp}})
                MATCH (parent:Person {{rnokpp: $parent_rnokpp}})
                MERGE (child)-[:{RelType.CHILD_OF.value}]->(parent)
                """,
                child_rnokpp=child_rnokpp,
                parent_rnokpp=parent_rnokpp,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def link_person_spouse_of_person(
        self,
        person1_rnokpp: str,
        person2_rnokpp: str,
        marriage_date: str | None = None,
    ) -> None:
        """
        Create bidirectional SPOUSE_OF relationship.
        WHY: Symmetric relationship - A is spouse of B means B is spouse of A.
        We create both directions for easier querying.
        """
        def _tx(tx):
            # Create both directions
            tx.run(
                f"""
                MATCH (p1:Person {{rnokpp: $person1_rnokpp}})
                MATCH (p2:Person {{rnokpp: $person2_rnokpp}})
                MERGE (p1)-[r1:{RelType.SPOUSE_OF.value}]->(p2)
                MERGE (p2)-[r2:{RelType.SPOUSE_OF.value}]->(p1)
                SET r1.marriage_date = $marriage_date,
                    r2.marriage_date = $marriage_date
                """,
                person1_rnokpp=person1_rnokpp,
                person2_rnokpp=person2_rnokpp,
                marriage_date=marriage_date,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    # ========================================================================
    # Income relationships (Person → IncomeRecord → Organization)
    # WHY split into two relationships instead of one direct link:
    # 1. IncomeRecord is a queryable fact node with many properties
    # 2. Allows efficient queries in both directions
    # 3. Clear money flow semantics: Person earned Income paid_by Organization
    # ========================================================================

    def link_person_earned_income(
        self,
        person_rnokpp: str,
        income_id: str,
    ) -> None:
        """
        Create EARNED_INCOME relationship (Person → IncomeRecord).
        WHY: Links person to their income record. IncomeRecord is the fact.
        """
        def _tx(tx):
            tx.run(
                f"""
                MATCH (p:Person {{rnokpp: $person_rnokpp}})
                MATCH (i:IncomeRecord {{income_id: $income_id}})
                MERGE (p)-[:{RelType.EARNED_INCOME.value}]->(i)
                """,
                person_rnokpp=person_rnokpp,
                income_id=income_id,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def link_income_paid_by_organization(
        self,
        income_id: str,
        org_edrpou: str,
    ) -> None:
        """
        Create PAID_BY relationship (IncomeRecord → Organization).
        WHY: Links income to the tax agent who paid it.
        """
        def _tx(tx):
            tx.run(
                f"""
                MATCH (i:IncomeRecord {{income_id: $income_id}})
                MATCH (o:Organization {{edrpou: $org_edrpou}})
                MERGE (i)-[:{RelType.PAID_BY.value}]->(o)
                """,
                income_id=income_id,
                org_edrpou=org_edrpou,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    # ========================================================================
    # Property relationships
    # ========================================================================

    def link_person_owns_property(
        self,
        person_rnokpp: str,
        property_id: str,
        ownership_type: str | None = None,
        since_date: str | None = None,
    ) -> None:
        """
        Create OWNS relationship (Person → Property).
        WHY: Direct ownership - person legally owns the property.
        """
        def _tx(tx):
            tx.run(
                f"""
                MATCH (p:Person {{rnokpp: $person_rnokpp}})
                MATCH (prop:Property {{property_id: $property_id}})
                MERGE (p)-[r:{RelType.OWNS.value}]->(prop)
                SET r.ownership_type = $ownership_type,
                    r.since_date = $since_date
                """,
                person_rnokpp=person_rnokpp,
                property_id=property_id,
                ownership_type=ownership_type,
                since_date=since_date,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    # ========================================================================
    # Power of Attorney relationships
    # ========================================================================

    def link_person_grantor_of_poa(
        self,
        person_rnokpp: str,
        poa_id: str,
    ) -> None:
        """
        Create GRANTOR_OF relationship (Person → PowerOfAttorney).
        WHY: Person granted the power of attorney to someone else.
        """
        def _tx(tx):
            tx.run(
                f"""
                MATCH (p:Person {{rnokpp: $person_rnokpp}})
                MATCH (poa:PowerOfAttorney {{poa_id: $poa_id}})
                MERGE (p)-[:{RelType.GRANTOR_OF.value}]->(poa)
                """,
                person_rnokpp=person_rnokpp,
                poa_id=poa_id,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def link_person_representative_of_poa(
        self,
        person_rnokpp: str,
        poa_id: str,
    ) -> None:
        """
        Create REPRESENTATIVE_OF relationship (Person → PowerOfAttorney).
        WHY: Person received power of attorney - can act on behalf of grantor.
        Critical for detecting hidden control.
        """
        def _tx(tx):
            tx.run(
                f"""
                MATCH (p:Person {{rnokpp: $person_rnokpp}})
                MATCH (poa:PowerOfAttorney {{poa_id: $poa_id}})
                MERGE (p)-[:{RelType.REPRESENTATIVE_OF.value}]->(poa)
                """,
                person_rnokpp=person_rnokpp,
                poa_id=poa_id,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def link_poa_authorizes_property(
        self,
        poa_id: str,
        property_id: str,
    ) -> None:
        """
        Create AUTHORIZES_PROPERTY relationship (PowerOfAttorney → Property).
        WHY: Power of attorney covers specific properties - shows control scope.
        """
        def _tx(tx):
            tx.run(
                f"""
                MATCH (poa:PowerOfAttorney {{poa_id: $poa_id}})
                MATCH (prop:Property {{property_id: $property_id}})
                MERGE (poa)-[:{RelType.AUTHORIZES_PROPERTY.value}]->(prop)
                """,
                poa_id=poa_id,
                property_id=property_id,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    # ========================================================================
    # Investigation relationships
    # ========================================================================

    def link_executor_created_request(
        self,
        executor_rnokpp: str,
        request_id: str,
    ) -> None:
        """
        Create CREATED_REQUEST relationship (Executor → Request).
        WHY: Audit trail - which investigator created which request.
        """
        def _tx(tx):
            tx.run(
                f"""
                MATCH (e:Executor {{executor_rnokpp: $executor_rnokpp}})
                MATCH (r:Request {{request_id: $request_id}})
                MERGE (e)-[:{RelType.CREATED_REQUEST.value}]->(r)
                """,
                executor_rnokpp=executor_rnokpp,
                request_id=request_id,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def link_request_subject_of_person(
        self,
        request_id: str,
        person_rnokpp: str,
    ) -> None:
        """
        Create SUBJECT_OF relationship (Request → Person).
        WHY: Links investigation request to the person being investigated.
        """
        def _tx(tx):
            tx.run(
                f"""
                MATCH (r:Request {{request_id: $request_id}})
                MATCH (p:Person {{rnokpp: $person_rnokpp}})
                MERGE (r)-[:{RelType.SUBJECT_OF.value}]->(p)
                """,
                request_id=request_id,
                person_rnokpp=person_rnokpp,
            )

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)
