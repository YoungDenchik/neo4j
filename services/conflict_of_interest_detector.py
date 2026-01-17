from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from neo4j import Driver

from core.neo4j_driver import get_driver, get_db_name
from domain.enums import OrganizationalLegalForm
from services.income_anomaly_detector import AnomalySeverity


@dataclass(frozen=True)
class ConflictOfInterestAnomaly:
    """
    Conflict-of-interest anomaly for a person.
    Structure mirrors IncomeAnomaly.
    """
    code: str
    severity: AnomalySeverity
    title: str
    description: str
    details: Dict[str, Any]
    person_rnokpp: str
    recommendation: str


@dataclass
class PersonConflictOfInterestAnalysis:
    """
    Conflict-of-interest analysis for a person.
    """
    person_rnokpp: str
    person_name: Optional[str] = None
    anomalies: List[ConflictOfInterestAnomaly] = field(default_factory=list)
    risk_score: float = 0.0  # 0–100
    analysis_summary: Dict[str, Any] = field(default_factory=dict)


class ConflictOfInterestDetector:
    """
    Detects structural conflict-of-interest patterns using current graph schema.

    Implemented now:
    1. Person is director of a government organization (olf_code in GOV codes)
       AND founder of at least one non-government organization.
       -> CRITICAL: CIVIL_SERVICE_AND_BUSINESS_FOUNDERSHIP

    NOTE:
    - This is a structural signal only (no employment periods yet).
    - When employment relations and dates appear in schema, this class can be
      extended to check temporal overlap.
    """

    def __init__(
        self,
        driver: Optional[Driver] = None,
        gov_olf_codes: Optional[List[str]] = None,
    ):
        self._driver = driver or get_driver()
        self._db = get_db_name()

        # By default, use ORGANIZATIONAL-LEGAL FORM "GOVERNMENT"
        self.gov_olf_codes = gov_olf_codes or [OrganizationalLegalForm.GOVERNMENT.value]

    def analyze_person(self, rnokpp: str) -> PersonConflictOfInterestAnalysis:
        """
        Run conflict-of-interest detection for a single person.
        """
        analysis = PersonConflictOfInterestAnalysis(person_rnokpp=rnokpp)

        person_info = self._get_person_info(rnokpp)
        if person_info:
            analysis.person_name = person_info.get("full_name")

        anomalies: List[ConflictOfInterestAnomaly] = []

        anomalies.extend(self._detect_gov_director_private_founder(rnokpp))

        analysis.anomalies = anomalies
        analysis.risk_score = self._calculate_risk_score(anomalies)

        analysis.analysis_summary = {
            "has_gov_director_private_founder_conflict": any(
                a.code == "CIVIL_SERVICE_AND_BUSINESS_FOUNDERSHIP" for a in anomalies
            ),
            "anomaly_count": len(anomalies),
        }

        return analysis

    def _detect_gov_director_private_founder(
        self,
        rnokpp: str,
    ) -> List[ConflictOfInterestAnomaly]:
        """
        Detect if the person is director of at least one government organization
        AND founder of at least one non-government organization.
        """
        anomalies: List[ConflictOfInterestAnomaly] = []

        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person {rnokpp: $rnokpp})

                // Government organizations where person is director
                OPTIONAL MATCH (p)-[:DIRECTOR_OF]->(gov:Organization)
                WHERE gov.olf_code IN $gov_olf_codes

                // Non-government organizations where person is founder
                OPTIONAL MATCH (p)-[:FOUNDER_OF]->(biz:Organization)
                WHERE biz.olf_code IS NULL OR NOT biz.olf_code IN $gov_olf_codes

                RETURN
                    collect(DISTINCT {
                        edrpou: gov.edrpou,
                        name: gov.name,
                        olf_code: gov.olf_code,
                        olf_name: gov.olf_name,
                        registration_date: gov.registration_date
                    }) AS gov_orgs,
                    collect(DISTINCT {
                        edrpou: biz.edrpou,
                        name: biz.name,
                        olf_code: biz.olf_code,
                        olf_name: biz.olf_name,
                        registration_date: biz.registration_date
                    }) AS private_orgs
                """,
                rnokpp=rnokpp,
                gov_olf_codes=self.gov_olf_codes,
            )
            record = result.single()
            return dict(record) if record else {"gov_orgs": [], "private_orgs": []}

        with self._driver.session(database=self._db) as session:
            raw = session.execute_read(_tx)

        gov_orgs_raw = raw.get("gov_orgs") or []
        private_orgs_raw = raw.get("private_orgs") or []

        gov_orgs = [
            g for g in gov_orgs_raw
            if g is not None and g.get("edrpou") is not None
        ]
        private_orgs = [
            b for b in private_orgs_raw
            if b is not None and b.get("edrpou") is not None
        ]

        if not gov_orgs or not private_orgs:
            return anomalies

        severity = AnomalySeverity.CRITICAL

        anomalies.append(
            ConflictOfInterestAnomaly(
                code="CIVIL_SERVICE_AND_BUSINESS_FOUNDERSHIP",
                severity=severity,
                title="Civil Service and Private Business Foundership Conflict",
                description=(
                    "Person acts as a director of at least one government organization "
                    "and is simultaneously a founder of at least one non-government "
                    "organization. This may represent a conflict of interest under "
                    "anti-corruption legislation."
                ),
                details={
                    "gov_organizations": gov_orgs,
                    "private_organizations": private_orgs,
                    "gov_count": len(gov_orgs),
                    "private_count": len(private_orgs),
                },
                person_rnokpp=rnokpp,
                recommendation=(
                    "Review compliance with anti-corruption and conflict-of-interest "
                    "rules. Check whether the combination of civil service role and "
                    "private foundership is legally permitted and properly declared."
                ),
            )
        )

        return anomalies

    def _get_person_info(self, rnokpp: str) -> Optional[Dict[str, Any]]:
        """
        Get simple person info (full name).
        """
        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person {rnokpp: $rnokpp})
                RETURN
                    p.last_name + ' ' +
                    p.first_name + ' ' +
                    coalesce(p.middle_name, '') AS full_name
                """,
                rnokpp=rnokpp,
            )
            record = result.single()
            return dict(record) if record else None

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    def _calculate_risk_score(
        self,
        anomalies: List[ConflictOfInterestAnomaly],
    ) -> float:
        if not anomalies:
            return 0.0

        severity_weights = {
            AnomalySeverity.LOW: 10,
            AnomalySeverity.MEDIUM: 25,
            AnomalySeverity.HIGH: 40,
            AnomalySeverity.CRITICAL: 60,
        }

        total_score = sum(severity_weights.get(a.severity, 10) for a in anomalies)
        return min(100.0, float(total_score))
