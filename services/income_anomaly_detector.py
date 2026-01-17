from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

from neo4j import Driver

from core.neo4j_driver import get_driver, get_db_name
from domain.enums import IncomeCategory


class AnomalySeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class IncomeAnomaly:
    """
    Represents a detected income anomaly.
    """
    code: str
    severity: AnomalySeverity
    title: str
    description: str
    details: Dict[str, Any]
    person_rnokpp: str
    recommendation: str


@dataclass
class PersonIncomeAnalysis:
    """
    Complete income analysis for a person.
    """
    person_rnokpp: str
    person_name: Optional[str] = None
    total_income: float = 0.0
    total_tax_paid: float = 0.0
    anomalies: List[IncomeAnomaly] = field(default_factory=list)
    risk_score: float = 0.0  # 0-100
    analysis_summary: Dict[str, Any] = field(default_factory=dict)


class IncomeAnomalyDetector:
    """
    Detects suspicious income patterns that may indicate money laundering,
    bribery, or tax evasion.

    Detection patterns:
    1. Income/Tax mismatch - accrued != paid or tax charged != transferred
    2. Concentrated income - large income from single source without employment
    3. Unusual income categories - high-value gifts, bonuses, other
    4. Income spikes - sudden jumps compared to historical baseline
    """

    def __init__(
        self,
        driver: Driver | None = None,
        # Thresholds (in UAH)
        income_mismatch_threshold: float = 1000.0,  # ignore tiny mismatches
        concentration_threshold: float = 100_000.0,  # single source threshold
        unusual_category_threshold: float = 50_000.0,  # gifts/bonuses threshold
        spike_multiplier: float = 3.0,  # income > 3x average = spike
    ):
        self._driver = driver or get_driver()
        self._db = get_db_name()

        self.income_mismatch_threshold = income_mismatch_threshold
        self.concentration_threshold = concentration_threshold
        self.unusual_category_threshold = unusual_category_threshold
        self.spike_multiplier = spike_multiplier

    def analyze_person(self, rnokpp: str) -> PersonIncomeAnalysis:
        """
        Run all income anomaly detection patterns for a single person.
        """
        analysis = PersonIncomeAnalysis(person_rnokpp=rnokpp)

        # Get person name
        person_info = self._get_person_info(rnokpp)
        if person_info:
            analysis.person_name = person_info.get("full_name")

        # Run all detection patterns
        anomalies = []

        # Pattern 1: Income/Tax mismatch
        anomalies.extend(self._detect_income_tax_mismatch(rnokpp))

        # Pattern 2: Concentrated income without employment relationship
        anomalies.extend(self._detect_concentrated_income(rnokpp))

        # Pattern 3: Unusual income categories
        anomalies.extend(self._detect_unusual_categories(rnokpp))

        # Pattern 4: Income spikes
        anomalies.extend(self._detect_income_spikes(rnokpp))

        analysis.anomalies = anomalies

        # Calculate risk score
        analysis.risk_score = self._calculate_risk_score(anomalies)

        # Get summary stats
        summary = self._get_income_summary(rnokpp)
        analysis.total_income = summary.get("total_income", 0.0)
        analysis.total_tax_paid = summary.get("total_tax", 0.0)
        analysis.analysis_summary = summary

        return analysis

    def scan_all_persons(self, limit: int = 1000) -> List[PersonIncomeAnalysis]:
        """
        Scan all persons in the database for income anomalies.
        Returns list sorted by risk score (highest first).
        """
        # Get all persons with income records
        persons = self._get_persons_with_income(limit)

        results = []
        for person in persons:
            analysis = self.analyze_person(person["rnokpp"])
            if analysis.anomalies:  # Only include persons with anomalies
                results.append(analysis)

        # Sort by risk score descending
        results.sort(key=lambda x: x.risk_score, reverse=True)
        return results

    # =========================================================================
    # Detection Pattern 1: Income/Tax Mismatch
    # =========================================================================

    def _detect_income_tax_mismatch(self, rnokpp: str) -> List[IncomeAnomaly]:
        """
        Detect records where income_accrued != income_paid
        or tax_charged != tax_transferred.
        """
        anomalies = []

        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person {rnokpp: $rnokpp})-[:EARNED_INCOME]->(i:IncomeRecord)-[:PAID_BY]->(o:Organization)
                WHERE abs(i.income_accrued - i.income_paid) > $threshold
                   OR abs(i.tax_charged - i.tax_transferred) > $threshold
                RETURN
                    i.income_id as income_id,
                    i.income_accrued as accrued,
                    i.income_paid as paid,
                    i.tax_charged as tax_charged,
                    i.tax_transferred as tax_transferred,
                    i.period_year as year,
                    i.period_quarter_month as period,
                    i.income_type_description as income_type,
                    o.edrpou as org_edrpou,
                    o.name as org_name
                ORDER BY abs(i.income_accrued - i.income_paid) DESC
                """,
                rnokpp=rnokpp,
                threshold=self.income_mismatch_threshold,
            )
            return list(result)

        with self._driver.session(database=self._db) as session:
            records = session.execute_read(_tx)

        # Aggregate mismatches
        total_unpaid_income = 0.0
        total_unpaid_tax = 0.0
        mismatch_records = []

        for record in records:
            income_diff = (record["accrued"] or 0) - (record["paid"] or 0)
            tax_diff = (record["tax_charged"] or 0) - (record["tax_transferred"] or 0)

            if abs(income_diff) > self.income_mismatch_threshold:
                total_unpaid_income += income_diff
                mismatch_records.append({
                    "year": record["year"],
                    "period": record["period"],
                    "org_name": record["org_name"],
                    "income_diff": income_diff,
                    "tax_diff": tax_diff,
                })

            if abs(tax_diff) > self.income_mismatch_threshold:
                total_unpaid_tax += tax_diff

        if mismatch_records:
            severity = AnomalySeverity.HIGH if total_unpaid_income > 100_000 else AnomalySeverity.MEDIUM

            anomalies.append(IncomeAnomaly(
                code="INCOME_TAX_MISMATCH",
                severity=severity,
                title="Income/Tax Payment Mismatch",
                description=f"Found {len(mismatch_records)} income records where accrued amount differs from paid amount",
                details={
                    "total_unpaid_income": total_unpaid_income,
                    "total_unpaid_tax": total_unpaid_tax,
                    "record_count": len(mismatch_records),
                    "records": mismatch_records[:10],  # Top 10
                },
                person_rnokpp=rnokpp,
                recommendation="Investigate tax compliance. May indicate unreported income or tax evasion.",
            ))

        return anomalies

    # =========================================================================
    # Detection Pattern 2: Concentrated Income
    # =========================================================================

    def _detect_concentrated_income(self, rnokpp: str) -> List[IncomeAnomaly]:
        """
        Detect large income from single organization where person
        has no employment relationship (DIRECTOR_OF or FOUNDER_OF).
        """
        anomalies = []

        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person {rnokpp: $rnokpp})-[:EARNED_INCOME]->(i:IncomeRecord)-[:PAID_BY]->(o:Organization)

                // Check if person has formal relationship with org
                OPTIONAL MATCH (p)-[dir:DIRECTOR_OF]->(o)
                OPTIONAL MATCH (p)-[fnd:FOUNDER_OF]->(o)

                WITH o,
                     sum(i.income_paid) as total_from_org,
                     count(i) as record_count,
                     collect(DISTINCT i.period_year) as years,
                     dir IS NOT NULL as is_director,
                     fnd IS NOT NULL as is_founder

                WHERE total_from_org > $threshold
                  AND NOT is_director
                  AND NOT is_founder

                RETURN
                    o.edrpou as org_edrpou,
                    o.name as org_name,
                    o.state as org_state,
                    o.state_text as org_state_text,
                    total_from_org,
                    record_count,
                    years,
                    is_director,
                    is_founder
                ORDER BY total_from_org DESC
                """,
                rnokpp=rnokpp,
                threshold=self.concentration_threshold,
            )
            return list(result)

        with self._driver.session(database=self._db) as session:
            records = session.execute_read(_tx)

        for record in records:
            # Higher severity for terminated/liquidating companies
            org_state = record["org_state"]
            is_suspicious_org = org_state in ("3", "2")  # terminated or in liquidation

            severity = AnomalySeverity.CRITICAL if is_suspicious_org else AnomalySeverity.HIGH

            anomalies.append(IncomeAnomaly(
                code="CONCENTRATED_INCOME_NO_EMPLOYMENT",
                severity=severity,
                title="Large Income Without Employment Relationship",
                description=f"Received {record['total_from_org']:,.0f} UAH from {record['org_name']} without being director or founder",
                details={
                    "organization_edrpou": record["org_edrpou"],
                    "organization_name": record["org_name"],
                    "organization_state": record["org_state_text"] or record["org_state"],
                    "total_income": record["total_from_org"],
                    "record_count": record["record_count"],
                    "years": record["years"],
                    "is_suspicious_org": is_suspicious_org,
                },
                person_rnokpp=rnokpp,
                recommendation="Verify the nature of payments. May indicate kickbacks, bribes, or undisclosed employment.",
            ))

        return anomalies

    # =========================================================================
    # Detection Pattern 3: Unusual Income Categories
    # =========================================================================

    def _detect_unusual_categories(self, rnokpp: str) -> List[IncomeAnomaly]:
        """
        Detect high-value income in categories commonly used to disguise
        illicit payments: gifts, bonuses, 'other'.
        """
        anomalies = []

        # Suspicious income type codes (common for disguising payments)
        # 126 - Додаткове благо (additional benefit/bonus)
        # 178 - Подарунки (gifts)
        # 186 - Інші доходи (other income)
        suspicious_codes = ["126", "178", "186"]

        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person {rnokpp: $rnokpp})-[:EARNED_INCOME]->(i:IncomeRecord)-[:PAID_BY]->(o:Organization)
                WHERE i.income_type_code IN $suspicious_codes
                  AND i.income_paid > $threshold

                RETURN
                    i.income_type_code as type_code,
                    i.income_type_description as type_description,
                    i.income_paid as amount,
                    i.period_year as year,
                    i.period_quarter_month as period,
                    o.edrpou as org_edrpou,
                    o.name as org_name
                ORDER BY i.income_paid DESC
                """,
                rnokpp=rnokpp,
                suspicious_codes=suspicious_codes,
                threshold=self.unusual_category_threshold,
            )
            return list(result)

        with self._driver.session(database=self._db) as session:
            records = session.execute_read(_tx)

        if records:
            total_suspicious = sum(r["amount"] for r in records)

            # Group by type
            by_type = {}
            for r in records:
                code = r["type_code"]
                if code not in by_type:
                    by_type[code] = {
                        "description": r["type_description"],
                        "total": 0,
                        "count": 0,
                        "sources": [],
                    }
                by_type[code]["total"] += r["amount"]
                by_type[code]["count"] += 1
                if r["org_name"] not in [s["name"] for s in by_type[code]["sources"]]:
                    by_type[code]["sources"].append({
                        "name": r["org_name"],
                        "edrpou": r["org_edrpou"],
                    })

            severity = AnomalySeverity.HIGH if total_suspicious > 200_000 else AnomalySeverity.MEDIUM

            anomalies.append(IncomeAnomaly(
                code="UNUSUAL_INCOME_CATEGORY",
                severity=severity,
                title="High-Value Income in Suspicious Categories",
                description=f"Received {total_suspicious:,.0f} UAH in gifts, bonuses, or 'other' income categories",
                details={
                    "total_suspicious_income": total_suspicious,
                    "record_count": len(records),
                    "by_category": by_type,
                    "top_records": [
                        {
                            "amount": r["amount"],
                            "type": r["type_description"],
                            "org": r["org_name"],
                            "year": r["year"],
                        }
                        for r in records[:5]
                    ],
                },
                person_rnokpp=rnokpp,
                recommendation="Review justification for non-salary payments. Categories commonly used to disguise bribes.",
            ))

        return anomalies

    # =========================================================================
    # Detection Pattern 4: Income Spikes
    # =========================================================================

    def _detect_income_spikes(self, rnokpp: str) -> List[IncomeAnomaly]:
        """
        Detect years where income significantly exceeds historical average.
        """
        anomalies = []

        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person {rnokpp: $rnokpp})-[:EARNED_INCOME]->(i:IncomeRecord)
                WITH p, i.period_year as year, sum(i.income_paid) as yearly_income
                ORDER BY year
                WITH collect({year: year, income: yearly_income}) as yearly_data

                // Calculate average (excluding max year to avoid self-comparison bias)
                WITH yearly_data,
                     reduce(total = 0.0, y IN yearly_data | total + y.income) / size(yearly_data) as avg_income

                UNWIND yearly_data as yd
                WITH yd.year as year, yd.income as income, avg_income
                WHERE income > avg_income * $multiplier
                  AND avg_income > 10000  // Ignore if average is very low

                RETURN year, income, avg_income, income / avg_income as spike_ratio
                ORDER BY spike_ratio DESC
                """,
                rnokpp=rnokpp,
                multiplier=self.spike_multiplier,
            )
            return list(result)

        with self._driver.session(database=self._db) as session:
            records = session.execute_read(_tx)

        for record in records:
            spike_ratio = record["spike_ratio"]
            severity = AnomalySeverity.HIGH if spike_ratio > 5 else AnomalySeverity.MEDIUM

            anomalies.append(IncomeAnomaly(
                code="INCOME_SPIKE",
                severity=severity,
                title=f"Abnormal Income Spike in {record['year']}",
                description=f"Income in {record['year']} was {spike_ratio:.1f}x the historical average",
                details={
                    "year": record["year"],
                    "year_income": record["income"],
                    "average_income": record["avg_income"],
                    "spike_ratio": spike_ratio,
                },
                person_rnokpp=rnokpp,
                recommendation="Investigate source of sudden income increase. May indicate one-time illicit payment.",
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

    def _get_income_summary(self, rnokpp: str) -> Dict[str, Any]:
        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person {rnokpp: $rnokpp})-[:EARNED_INCOME]->(i:IncomeRecord)-[:PAID_BY]->(o:Organization)
                RETURN
                    sum(i.income_paid) as total_income,
                    sum(i.tax_transferred) as total_tax,
                    count(DISTINCT o) as source_count,
                    count(i) as record_count,
                    collect(DISTINCT i.period_year) as years
                """,
                rnokpp=rnokpp,
            )
            record = result.single()
            return dict(record) if record else {}

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    def _get_persons_with_income(self, limit: int) -> List[Dict[str, Any]]:
        def _tx(tx):
            result = tx.run(
                """
                MATCH (p:Person)-[:EARNED_INCOME]->(i:IncomeRecord)
                WITH p, sum(i.income_paid) as total_income
                WHERE total_income > 0
                RETURN p.rnokpp as rnokpp, total_income
                ORDER BY total_income DESC
                LIMIT $limit
                """,
                limit=limit,
            )
            return [dict(r) for r in result]

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    def _calculate_risk_score(self, anomalies: List[IncomeAnomaly]) -> float:
        """
        Calculate overall risk score (0-100) based on anomalies.
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

        # Cap at 100
        return min(100.0, total_score)
