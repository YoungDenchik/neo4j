"""
Shared Household Detector (Спільний побут)

Detects patterns that may indicate undeclared cohabitation/civil marriage
between a PEP (politically exposed person) and another person.

If an official and a "stranger" frequently appear together in documents,
this may indicate a civil partnership that should be declared but is hidden.

Data sources used:
- Power of attorney documents (official gave PoA to non-family member)
- Shared address registration
- Common organizational connections
- Border crossing patterns (if available)

Detection logic:
- Find persons who frequently co-occur with an official in legal/financial documents
- Exclude official family members (spouse, children, parents)
- Flag high-frequency co-occurrence as potential undeclared relationship
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from neo4j import Driver

from core.neo4j_driver import get_driver, get_db_name
from services.income_anomaly_detector import AnomalySeverity


@dataclass(frozen=True)
class SharedHouseholdAnomaly:
    """
    Represents a detected shared household anomaly.
    """
    code: str
    severity: AnomalySeverity
    title: str
    description: str
    details: Dict[str, Any]
    official_rnokpp: str
    suspect_rnokpp: str
    recommendation: str


@dataclass
class SharedHouseholdAnalysis:
    """
    Analysis results for shared household detection.
    """
    official_rnokpp: str
    official_name: Optional[str] = None
    anomalies: List[SharedHouseholdAnomaly] = field(default_factory=list)
    risk_score: float = 0.0
    analysis_summary: Dict[str, Any] = field(default_factory=dict)


class SharedHouseholdDetector:
    """
    Detects patterns indicating undeclared cohabitation between officials
    and non-family members.

    Detection patterns:
    1. POA_TO_STRANGER - Official gave PoA (especially for vehicle) to non-family member
    2. MULTIPLE_POA_CONNECTIONS - Multiple PoA documents between same two persons
    3. SHARED_ADDRESS - Official and non-family member share same address
    4. SHARED_ORGANIZATION - Official and non-family member both connected to same orgs
    """

    def __init__(
        self,
        driver: Driver | None = None,
        # Thresholds
        min_connection_count: int = 2,  # Minimum document connections to flag
    ):
        self._driver = driver or get_driver()
        self._db = get_db_name()

        self.min_connection_count = min_connection_count

    def analyze_official(self, rnokpp: str) -> SharedHouseholdAnalysis:
        """
        Analyze a specific official for shared household patterns.
        """
        analysis = SharedHouseholdAnalysis(official_rnokpp=rnokpp)

        person_info = self._get_person_info(rnokpp)
        if person_info:
            analysis.official_name = person_info.get("full_name")

        anomalies = []

        # Pattern 1: PoA to non-family members (especially for vehicles)
        anomalies.extend(self._detect_poa_to_stranger(rnokpp))

        # Pattern 2: Multiple PoA connections with same person
        anomalies.extend(self._detect_multiple_poa_connections(rnokpp))

        # Pattern 3: Shared address with non-family
        anomalies.extend(self._detect_shared_address(rnokpp))

        # Pattern 4: Shared organizational connections with frequent co-occurrence
        anomalies.extend(self._detect_shared_organizations(rnokpp))

        analysis.anomalies = anomalies
        analysis.risk_score = self._calculate_risk_score(anomalies)

        analysis.analysis_summary = {
            "poa_to_stranger_count": len([a for a in anomalies if a.code == "POA_TO_STRANGER"]),
            "multiple_poa_count": len([a for a in anomalies if a.code == "MULTIPLE_POA_CONNECTIONS"]),
            "shared_address_count": len([a for a in anomalies if a.code == "SHARED_ADDRESS"]),
            "shared_org_count": len([a for a in anomalies if a.code == "SHARED_ORGANIZATION"]),
            "total_anomalies": len(anomalies),
        }

        return analysis

    def scan_all_officials(self, limit: int = 100) -> List[SharedHouseholdAnalysis]:
        """
        Scan all officials in the database for shared household patterns.
        """
        officials = self._get_all_officials(limit)

        results = []
        for official in officials:
            analysis = self.analyze_official(official["rnokpp"])
            if analysis.anomalies:
                results.append(analysis)

        results.sort(key=lambda x: x.risk_score, reverse=True)
        return results

    # =========================================================================
    # Detection Pattern 1: PoA to Stranger
    # =========================================================================

    def _detect_poa_to_stranger(self, official_rnokpp: str) -> List[SharedHouseholdAnomaly]:
        """
        Find cases where official gave PoA to someone who is not a declared family member.
        Especially suspicious for vehicle PoAs.
        """
        anomalies = []

        def _tx(tx):
            result = tx.run(
                """
                MATCH (official:Person {rnokpp: $rnokpp})

                // Find PoAs where official is the grantor
                MATCH (poa:PowerOfAttorney)-[:HAS_GRANTOR]->(official)
                MATCH (poa)-[:HAS_REPRESENTATIVE]->(representative:Person)
                WHERE representative.rnokpp <> official.rnokpp

                // Exclude declared family members
                OPTIONAL MATCH (official)-[:SPOUSE_OF]-(representative)
                OPTIONAL MATCH (official)-[:CHILD_OF]-(representative)
                OPTIONAL MATCH (representative)-[:CHILD_OF]-(official)

                WITH official, poa, representative,
                     NOT (official)-[:SPOUSE_OF]-(representative) AND
                     NOT (official)-[:CHILD_OF]-(representative) AND
                     NOT (representative)-[:CHILD_OF]-(official) as is_stranger

                WHERE is_stranger = true

                // Check if PoA is for a property (vehicle/real estate)
                OPTIONAL MATCH (poa)-[:HAS_PROPERTY]->(prop:Property)

                RETURN
                    representative.rnokpp as rep_rnokpp,
                    representative.last_name + ' ' + representative.first_name + ' ' + coalesce(representative.middle_name, '') as rep_name,
                    poa.poa_id as poa_id,
                    poa.attested_date as poa_date,
                    prop.property_type as property_type,
                    prop.description as property_description,
                    prop IS NOT NULL as has_property
                """,
                rnokpp=official_rnokpp,
            )
            return list(result)

        with self._driver.session(database=self._db) as session:
            records = session.execute_read(_tx)

        for record in records:
            # Vehicle PoAs to strangers are more suspicious
            is_vehicle = record["property_type"] == "VEHICLE" if record["property_type"] else False
            severity = AnomalySeverity.HIGH if is_vehicle else AnomalySeverity.MEDIUM

            property_desc = f" for {record['property_type']}" if record["has_property"] else ""

            anomalies.append(SharedHouseholdAnomaly(
                code="POA_TO_STRANGER",
                severity=severity,
                title=f"Power of Attorney to Non-Family Member{property_desc}",
                description=(
                    f"Official gave PoA{property_desc} to {record['rep_name']} "
                    f"who is not a declared family member"
                ),
                details={
                    "representative_rnokpp": record["rep_rnokpp"],
                    "representative_name": record["rep_name"],
                    "poa_id": record["poa_id"],
                    "poa_date": record["poa_date"],
                    "property_type": record["property_type"],
                    "property_description": record["property_description"],
                    "is_vehicle_poa": is_vehicle,
                },
                official_rnokpp=official_rnokpp,
                suspect_rnokpp=record["rep_rnokpp"],
                recommendation=(
                    "Verify the relationship between official and representative. "
                    "If in long-term cohabitation, this should be declared. "
                    "Check for shared travel, address, or financial patterns."
                ),
            ))

        return anomalies

    # =========================================================================
    # Detection Pattern 2: Multiple PoA Connections
    # =========================================================================

    def _detect_multiple_poa_connections(self, official_rnokpp: str) -> List[SharedHouseholdAnomaly]:
        """
        Find persons with multiple PoA document connections to the official.
        Multiple legal documents between same persons suggests close relationship.
        """
        anomalies = []

        def _tx(tx):
            result = tx.run(
                """
                MATCH (official:Person {rnokpp: $rnokpp})

                // Find all PoAs involving official and another person
                MATCH (poa:PowerOfAttorney)
                WHERE (poa)-[:HAS_GRANTOR]->(official) OR (poa)-[:HAS_REPRESENTATIVE]->(official)

                MATCH (poa)-[:HAS_GRANTOR|HAS_REPRESENTATIVE]->(other:Person)
                WHERE other.rnokpp <> official.rnokpp

                // Exclude declared family
                OPTIONAL MATCH (official)-[:SPOUSE_OF]-(other)
                OPTIONAL MATCH (official)-[:CHILD_OF]-(other)
                OPTIONAL MATCH (other)-[:CHILD_OF]-(official)

                WITH official, other,
                     NOT (official)-[:SPOUSE_OF]-(other) AND
                     NOT (official)-[:CHILD_OF]-(other) AND
                     NOT (other)-[:CHILD_OF]-(official) as is_stranger,
                     count(poa) as poa_count,
                     collect(poa.poa_id) as poa_ids,
                     collect(poa.attested_date) as poa_dates

                WHERE is_stranger = true AND poa_count >= $min_count

                RETURN
                    other.rnokpp as other_rnokpp,
                    other.last_name + ' ' + other.first_name + ' ' + coalesce(other.middle_name, '') as other_name,
                    poa_count,
                    poa_ids,
                    poa_dates
                ORDER BY poa_count DESC
                """,
                rnokpp=official_rnokpp,
                min_count=self.min_connection_count,
            )
            return list(result)

        with self._driver.session(database=self._db) as session:
            records = session.execute_read(_tx)

        for record in records:
            poa_count = record["poa_count"]
            severity = AnomalySeverity.CRITICAL if poa_count >= 3 else AnomalySeverity.HIGH

            anomalies.append(SharedHouseholdAnomaly(
                code="MULTIPLE_POA_CONNECTIONS",
                severity=severity,
                title=f"Multiple PoA Documents with Same Non-Family Person",
                description=(
                    f"Official has {poa_count} PoA documents involving {record['other_name']} "
                    f"who is not a declared family member"
                ),
                details={
                    "suspect_rnokpp": record["other_rnokpp"],
                    "suspect_name": record["other_name"],
                    "poa_count": poa_count,
                    "poa_ids": record["poa_ids"][:10],
                    "poa_dates": record["poa_dates"][:10],
                },
                official_rnokpp=official_rnokpp,
                suspect_rnokpp=record["other_rnokpp"],
                recommendation=(
                    "High frequency of legal documents between two persons indicates "
                    "close relationship. Verify if this is undeclared civil partnership."
                ),
            ))

        return anomalies

    # =========================================================================
    # Detection Pattern 3: Shared Address
    # =========================================================================

    def _detect_shared_address(self, official_rnokpp: str) -> List[SharedHouseholdAnomaly]:
        """
        Find non-family members who share the same registered address.
        """
        anomalies = []

        def _tx(tx):
            result = tx.run(
                """
                MATCH (official:Person {rnokpp: $rnokpp})

                // Find addresses associated with official
                // This could be via REGISTERED_AT relationship or address property
                MATCH (official)-[:REGISTERED_AT]->(addr:Address)<-[:REGISTERED_AT]-(other:Person)
                WHERE other.rnokpp <> official.rnokpp

                // Exclude declared family
                OPTIONAL MATCH (official)-[:SPOUSE_OF]-(other)
                OPTIONAL MATCH (official)-[:CHILD_OF]-(other)
                OPTIONAL MATCH (other)-[:CHILD_OF]-(official)

                WITH official, other, addr,
                     NOT (official)-[:SPOUSE_OF]-(other) AND
                     NOT (official)-[:CHILD_OF]-(other) AND
                     NOT (other)-[:CHILD_OF]-(official) as is_stranger

                WHERE is_stranger = true

                RETURN
                    other.rnokpp as other_rnokpp,
                    other.last_name + ' ' + other.first_name + ' ' + coalesce(other.middle_name, '') as other_name,
                    addr.full_text as address,
                    addr.address_id as address_id
                """,
                rnokpp=official_rnokpp,
            )
            return list(result)

        with self._driver.session(database=self._db) as session:
            records = session.execute_read(_tx)

        for record in records:
            anomalies.append(SharedHouseholdAnomaly(
                code="SHARED_ADDRESS",
                severity=AnomalySeverity.HIGH,
                title="Shared Address with Non-Family Member",
                description=(
                    f"Official shares registered address with {record['other_name']} "
                    f"who is not a declared family member"
                ),
                details={
                    "suspect_rnokpp": record["other_rnokpp"],
                    "suspect_name": record["other_name"],
                    "address": record["address"],
                    "address_id": record["address_id"],
                },
                official_rnokpp=official_rnokpp,
                suspect_rnokpp=record["other_rnokpp"],
                recommendation=(
                    "Shared address is strong indicator of cohabitation. "
                    "Verify if this is undeclared civil partnership that should be disclosed."
                ),
            ))

        return anomalies

    # =========================================================================
    # Detection Pattern 4: Shared Organizations
    # =========================================================================

    def _detect_shared_organizations(self, official_rnokpp: str) -> List[SharedHouseholdAnomaly]:
        """
        Find non-family members who are connected to the same organizations
        as the official (both as directors, founders, or employees).
        """
        anomalies = []

        def _tx(tx):
            result = tx.run(
                """
                MATCH (official:Person {rnokpp: $rnokpp})

                // Find orgs where official is director or founder
                MATCH (official)-[:DIRECTOR_OF|FOUNDER_OF]->(org:Organization)

                // Find others connected to same orgs
                MATCH (other:Person)-[:DIRECTOR_OF|FOUNDER_OF]->(org)
                WHERE other.rnokpp <> official.rnokpp

                // Exclude declared family
                OPTIONAL MATCH (official)-[:SPOUSE_OF]-(other)
                OPTIONAL MATCH (official)-[:CHILD_OF]-(other)
                OPTIONAL MATCH (other)-[:CHILD_OF]-(official)

                WITH official, other,
                     NOT (official)-[:SPOUSE_OF]-(other) AND
                     NOT (official)-[:CHILD_OF]-(other) AND
                     NOT (other)-[:CHILD_OF]-(official) as is_stranger,
                     count(DISTINCT org) as shared_org_count,
                     collect(DISTINCT org.name) as org_names,
                     collect(DISTINCT org.edrpou) as org_codes

                WHERE is_stranger = true AND shared_org_count >= $min_count

                RETURN
                    other.rnokpp as other_rnokpp,
                    other.last_name + ' ' + other.first_name + ' ' + coalesce(other.middle_name, '') as other_name,
                    shared_org_count,
                    org_names,
                    org_codes
                ORDER BY shared_org_count DESC
                """,
                rnokpp=official_rnokpp,
                min_count=self.min_connection_count,
            )
            return list(result)

        with self._driver.session(database=self._db) as session:
            records = session.execute_read(_tx)

        for record in records:
            org_count = record["shared_org_count"]
            severity = AnomalySeverity.MEDIUM if org_count < 3 else AnomalySeverity.HIGH

            anomalies.append(SharedHouseholdAnomaly(
                code="SHARED_ORGANIZATION",
                severity=severity,
                title="Multiple Shared Organizations with Non-Family Member",
                description=(
                    f"Official and {record['other_name']} are both connected to "
                    f"{org_count} organization(s)"
                ),
                details={
                    "suspect_rnokpp": record["other_rnokpp"],
                    "suspect_name": record["other_name"],
                    "shared_org_count": org_count,
                    "organization_names": record["org_names"][:5],
                    "organization_codes": record["org_codes"][:5],
                },
                official_rnokpp=official_rnokpp,
                suspect_rnokpp=record["other_rnokpp"],
                recommendation=(
                    "Multiple shared organizational connections may indicate "
                    "undisclosed business partnership or personal relationship. "
                    "Verify if conflict of interest declaration is required."
                ),
            ))

        return anomalies

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _get_person_info(self, rnokpp: str) -> Optional[Dict[str, Any]]:
        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person {rnokpp: $rnokpp})
                RETURN p.last_name + ' ' + p.first_name + ' ' + coalesce(p.middle_name, '') as full_name
                """,
                rnokpp=rnokpp,
            )
            record = result.single()
            return dict(record) if record else None

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    def _get_all_officials(self, limit: int) -> List[Dict[str, Any]]:
        """Get all persons who could be officials (have corporate/PoA connections)."""
        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person)
                WHERE (p)-[:DIRECTOR_OF|FOUNDER_OF]->(:Organization)
                   OR (p)<-[:HAS_GRANTOR]-(:PowerOfAttorney)
                RETURN DISTINCT p.rnokpp as rnokpp
                LIMIT $limit
                """,
                limit=limit,
            )
            return [dict(r) for r in result]

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    def _calculate_risk_score(self, anomalies: List[SharedHouseholdAnomaly]) -> float:
        """Calculate risk score based on anomalies."""
        if not anomalies:
            return 0.0

        severity_weights = {
            AnomalySeverity.LOW: 10,
            AnomalySeverity.MEDIUM: 25,
            AnomalySeverity.HIGH: 40,
            AnomalySeverity.CRITICAL: 60,
        }

        total_score = sum(severity_weights.get(a.severity, 10) for a in anomalies)
        return min(100.0, total_score)
