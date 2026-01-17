from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from neo4j import Driver

from core.neo4j_driver import get_driver, get_db_name
from services.income_anomaly_detector import AnomalySeverity


@dataclass(frozen=True)
class IdentityAnomaly:
    """
    Identity-related anomaly for a person.
    Structure intentionally mirrors IncomeAnomaly.
    """
    code: str
    severity: AnomalySeverity
    title: str
    description: str
    details: Dict[str, Any]
    person_rnokpp: str
    recommendation: str


@dataclass
class PersonIdentityAnalysis:
    """
    Identity analysis for a person.
    """
    person_rnokpp: str
    person_name: Optional[str] = None
    anomalies: List[IdentityAnomaly] = field(default_factory=list)
    risk_score: float = 0.0  # 0–100
    analysis_summary: Dict[str, Any] = field(default_factory=dict)


class IdentityAnomalyDetector:
    """
    Detects identity-level anomalies.

    Implemented now (with current schema):

    1. RNOKPP collision:
       Same (last_name, first_name, middle_name, date_birth),
       but >1 distinct RNOKPP in the graph.

       -> CRITICAL: IDENTITY_RNOKPP_COLLISION
    """

    def __init__(self, driver: Optional[Driver] = None):
        self._driver = driver or get_driver()
        self._db = get_db_name()

    def analyze_person(self, rnokpp: str) -> PersonIdentityAnalysis:
        """
        Run all identity anomaly detection patterns for a single person.
        """
        analysis = PersonIdentityAnalysis(person_rnokpp=rnokpp)

        person_info = self._get_person_info(rnokpp)
        if person_info:
            analysis.person_name = person_info.get("full_name")

        anomalies: List[IdentityAnomaly] = []

        # Pattern 1: RNOKPP collision (same FIO + DOB, multiple RNOKPPs)
        anomalies.extend(self._detect_rnokpp_collision(rnokpp))

        analysis.anomalies = anomalies
        analysis.risk_score = self._calculate_risk_score(anomalies)

        # Simple summary for debugging / UI
        analysis.analysis_summary = {
            "has_rnokpp_collision": any(
                a.code == "IDENTITY_RNOKPP_COLLISION" for a in anomalies
            ),
            "anomaly_count": len(anomalies),
        }

        return analysis

    def _detect_rnokpp_collision(self, rnokpp: str) -> List[IdentityAnomaly]:
        """
        Detect if there are multiple RNOKPPs for the same
        (last_name, first_name, middle_name, date_birth) tuple.
        """
        anomalies: List[IdentityAnomaly] = []

        identity_key = self._get_person_identity_key(rnokpp)
        if identity_key is None:
            return anomalies

        if not identity_key.get("date_birth"):
            return anomalies

        def _tx(tx):
            result = tx.run(
                """
                MATCH (target:Person {rnokpp: $rnokpp})
                WITH target.last_name AS ln,
                     target.first_name AS fn,
                     target.middle_name AS mn,
                     target.date_birth AS dob

                MATCH (other:Person)
                WHERE other.last_name = ln
                  AND other.first_name = fn
                  AND coalesce(other.middle_name, "") = coalesce(mn, "")
                  AND other.date_birth = dob

                RETURN
                    other.rnokpp AS rnokpp,
                    other.last_name AS last_name,
                    other.first_name AS first_name,
                    other.middle_name AS middle_name,
                    other.date_birth AS date_birth
                """,
                rnokpp=rnokpp,
            )
            return list(result)

        with self._driver.session(database=self._db) as session:
            records = session.execute_read(_tx)

        rnokpps = sorted({r["rnokpp"] for r in records if r["rnokpp"]})
        if len(rnokpps) <= 1:
            return anomalies

        severity = AnomalySeverity.CRITICAL

        anomalies.append(
            IdentityAnomaly(
                code="IDENTITY_RNOKPP_COLLISION",
                severity=severity,
                title="Multiple RNOKPP for Same Identity",
                description=(
                    "Detected multiple distinct RNOKPP values for the same "
                    "full name and date of birth. This may indicate manipulation "
                    "with tax IDs or duplicate identity records."
                ),
                details={
                    "identity_key": identity_key,
                    "rnokpp_values": rnokpps,
                    "count": len(rnokpps),
                },
                person_rnokpp=rnokpp,
                recommendation=(
                    "Verify which RNOKPP is legitimate for this person. "
                    "Check source systems (DRFO/DMS/NAZK) and audit how multiple "
                    "tax IDs were issued for the same individual."
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

    def _get_all_persons(self):
        def _tx(tx):
            result = tx.run(
                "MATCH (p:Person) RETURN p.rnokpp AS rnokpp"
            )
            return [dict(r) for r in result]

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    def _get_person_identity_key(self, rnokpp: str) -> Optional[Dict[str, Any]]:
        """
        Return the identity tuple used for collision detection:
        (last_name, first_name, middle_name, date_birth).
        """
        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person {rnokpp: $rnokpp})
                RETURN
                    p.last_name AS last_name,
                    p.first_name AS first_name,
                    p.middle_name AS middle_name,
                    p.date_birth AS date_birth
                """,
                rnokpp=rnokpp,
            )
            record = result.single()
            return dict(record) if record else None

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    def _calculate_risk_score(self, anomalies: List[IdentityAnomaly]) -> float:
        """
        Same scoring policy as income detector.
        """
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
