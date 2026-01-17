"""
Surrogate Wallet Detector (Гаманець оточення)

Detects patterns where a low-income person owns luxury assets that are
controlled or used by a PEP (politically exposed person) through power of attorney.

Pattern: An official doesn't register assets in their own name. Instead,
they register assets on trusted proxies (drivers, guards, distant relatives)
while maintaining control through power of attorney.

Graph pattern:
    (Official:Person {is_pep: true})<-[:HAS_REPRESENTATIVE]-(poa:PowerOfAttorney)
    (poa)-[:HAS_PROPERTY]->(asset:Property)
    (proxy:Person)-[:OWNS]->(asset)
    WHERE proxy has low official income
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from neo4j import Driver

from core.neo4j_driver import get_driver, get_db_name
from services.income_anomaly_detector import AnomalySeverity


@dataclass(frozen=True)
class SurrogateWalletAnomaly:
    """
    Represents a detected surrogate wallet anomaly.
    """
    code: str
    severity: AnomalySeverity
    title: str
    description: str
    details: Dict[str, Any]
    official_rnokpp: str
    proxy_rnokpp: str
    recommendation: str


@dataclass
class SurrogateWalletAnalysis:
    """
    Analysis results for surrogate wallet detection.
    """
    official_rnokpp: str
    official_name: Optional[str] = None
    anomalies: List[SurrogateWalletAnomaly] = field(default_factory=list)
    risk_score: float = 0.0
    analysis_summary: Dict[str, Any] = field(default_factory=dict)


class SurrogateWalletDetector:
    """
    Detects surrogate wallet patterns where low-income proxies hold
    assets controlled by PEPs through power of attorney.

    Detection patterns:
    1. POA_ASSET_PROXY - Official has PoA for asset owned by low-income person
    2. LOW_INCOME_LUXURY_OWNER - Person with low income owns high-value assets
       with suspicious connections to officials
    """

    def __init__(
        self,
        driver: Driver | None = None,
        # Thresholds
        low_income_threshold: float = 100_000.0,  # Annual income below this is "low"
        luxury_vehicle_threshold: float = 500_000.0,  # Vehicle value threshold
        luxury_realestate_threshold: float = 2_000_000.0,  # Real estate value threshold
    ):
        self._driver = driver or get_driver()
        self._db = get_db_name()

        self.low_income_threshold = low_income_threshold
        self.luxury_vehicle_threshold = luxury_vehicle_threshold
        self.luxury_realestate_threshold = luxury_realestate_threshold

    def analyze_official(self, rnokpp: str) -> SurrogateWalletAnalysis:
        """
        Analyze a specific official/PEP for surrogate wallet patterns.
        """
        analysis = SurrogateWalletAnalysis(official_rnokpp=rnokpp)

        person_info = self._get_person_info(rnokpp)
        if person_info:
            analysis.official_name = person_info.get("full_name")

        anomalies = []

        # Pattern 1: Official has PoA for assets owned by low-income proxies
        anomalies.extend(self._detect_poa_asset_proxy(rnokpp))

        # Pattern 2: Find low-income persons connected to official who own valuable assets
        anomalies.extend(self._detect_connected_low_income_owners(rnokpp))

        analysis.anomalies = anomalies
        analysis.risk_score = self._calculate_risk_score(anomalies)

        analysis.analysis_summary = {
            "poa_proxy_count": len([a for a in anomalies if a.code == "POA_ASSET_PROXY"]),
            "connected_low_income_count": len([a for a in anomalies if a.code == "CONNECTED_LOW_INCOME_LUXURY_OWNER"]),
            "total_anomalies": len(anomalies),
        }

        return analysis

    def scan_all_officials(self, limit: int = 100) -> List[SurrogateWalletAnalysis]:
        """
        Scan all PEPs/officials in the database for surrogate wallet patterns.
        Returns list sorted by risk score (highest first).
        """
        officials = self._get_all_officials(limit)

        results = []
        for official in officials:
            analysis = self.analyze_official(official["rnokpp"])
            if analysis.anomalies:
                results.append(analysis)

        results.sort(key=lambda x: x.risk_score, reverse=True)
        return results

    def scan_all_proxies(self, limit: int = 500) -> List[SurrogateWalletAnalysis]:
        """
        Alternative scan: find all potential proxies (low-income asset owners)
        and trace back to connected officials.
        """
        anomalies = self._detect_all_suspicious_proxies(limit)

        # Group by official
        by_official: Dict[str, List[SurrogateWalletAnomaly]] = {}
        for anomaly in anomalies:
            official = anomaly.official_rnokpp
            if official not in by_official:
                by_official[official] = []
            by_official[official].append(anomaly)

        results = []
        for official_rnokpp, official_anomalies in by_official.items():
            analysis = SurrogateWalletAnalysis(
                official_rnokpp=official_rnokpp,
                anomalies=official_anomalies,
                risk_score=self._calculate_risk_score(official_anomalies),
            )
            person_info = self._get_person_info(official_rnokpp)
            if person_info:
                analysis.official_name = person_info.get("full_name")
            results.append(analysis)

        results.sort(key=lambda x: x.risk_score, reverse=True)
        return results

    # =========================================================================
    # Detection Pattern 1: PoA Asset Proxy
    # =========================================================================

    def _detect_poa_asset_proxy(self, official_rnokpp: str) -> List[SurrogateWalletAnomaly]:
        """
        Find assets where:
        - Official has power of attorney (is representative)
        - Asset is owned by a different person (proxy)
        - Proxy has low official income
        """
        anomalies = []

        def _tx(tx):
            result = tx.run(
                """
                MATCH (official:Person {rnokpp: $rnokpp})

                // Official is the representative in a PoA
                MATCH (poa:PowerOfAttorney)-[:HAS_REPRESENTATIVE]->(official)

                // PoA is for a specific property
                MATCH (poa)-[:HAS_PROPERTY]->(asset:Property)

                // Property is owned by someone else (the proxy)
                MATCH (proxy:Person)-[:OWNS]->(asset)
                WHERE proxy.rnokpp <> official.rnokpp

                // Get proxy's total income
                OPTIONAL MATCH (proxy)-[:EARNED_INCOME]->(inc:IncomeRecord)
                WITH official, poa, asset, proxy,
                     sum(inc.income_paid) as proxy_total_income

                // Filter for low-income proxies
                WHERE proxy_total_income < $low_income_threshold
                   OR proxy_total_income IS NULL

                RETURN
                    proxy.rnokpp as proxy_rnokpp,
                    proxy.last_name + ' ' + proxy.first_name + ' ' + coalesce(proxy.middle_name, '') as proxy_name,
                    proxy_total_income,
                    asset.property_id as asset_id,
                    asset.property_type as asset_type,
                    asset.description as asset_description,
                    poa.poa_id as poa_id,
                    poa.attested_date as poa_date
                """,
                rnokpp=official_rnokpp,
                low_income_threshold=self.low_income_threshold,
            )
            return list(result)

        with self._driver.session(database=self._db) as session:
            records = session.execute_read(_tx)

        for record in records:
            proxy_income = record["proxy_total_income"] or 0

            severity = AnomalySeverity.CRITICAL if proxy_income == 0 else AnomalySeverity.HIGH

            anomalies.append(SurrogateWalletAnomaly(
                code="POA_ASSET_PROXY",
                severity=severity,
                title="Power of Attorney for Asset Owned by Low-Income Proxy",
                description=(
                    f"Official has PoA for {record['asset_type']} owned by "
                    f"{record['proxy_name']} whose total income is {proxy_income:,.0f} UAH"
                ),
                details={
                    "proxy_rnokpp": record["proxy_rnokpp"],
                    "proxy_name": record["proxy_name"],
                    "proxy_total_income": proxy_income,
                    "asset_id": record["asset_id"],
                    "asset_type": record["asset_type"],
                    "asset_description": record["asset_description"],
                    "poa_id": record["poa_id"],
                    "poa_date": record["poa_date"],
                },
                official_rnokpp=official_rnokpp,
                proxy_rnokpp=record["proxy_rnokpp"],
                recommendation=(
                    "Investigate the relationship between official and proxy. "
                    "Verify source of funds for asset acquisition. "
                    "Check if asset is being used by official."
                ),
            ))

        return anomalies

    # =========================================================================
    # Detection Pattern 2: Connected Low-Income Luxury Owners
    # =========================================================================

    def _detect_connected_low_income_owners(self, official_rnokpp: str) -> List[SurrogateWalletAnomaly]:
        """
        Find persons connected to the official (via PoA grantor relationship)
        who have low income but own valuable assets.
        """
        anomalies = []

        def _tx(tx):
            result = tx.run(
                """
                MATCH (official:Person {rnokpp: $rnokpp})

                // Find PoAs where official is grantor (gave PoA to someone)
                MATCH (poa:PowerOfAttorney)-[:HAS_GRANTOR]->(official)
                MATCH (poa)-[:HAS_REPRESENTATIVE]->(proxy:Person)
                WHERE proxy.rnokpp <> official.rnokpp

                // Check proxy's assets
                MATCH (proxy)-[:OWNS]->(asset:Property)

                // Get proxy's income
                OPTIONAL MATCH (proxy)-[:EARNED_INCOME]->(inc:IncomeRecord)
                WITH official, poa, proxy, asset,
                     sum(inc.income_paid) as proxy_total_income

                WHERE proxy_total_income < $low_income_threshold
                   OR proxy_total_income IS NULL

                RETURN
                    proxy.rnokpp as proxy_rnokpp,
                    proxy.last_name + ' ' + proxy.first_name + ' ' + coalesce(proxy.middle_name, '') as proxy_name,
                    proxy_total_income,
                    collect({
                        asset_id: asset.property_id,
                        asset_type: asset.property_type,
                        description: asset.description
                    }) as assets,
                    count(asset) as asset_count
                """,
                rnokpp=official_rnokpp,
                low_income_threshold=self.low_income_threshold,
            )
            return list(result)

        with self._driver.session(database=self._db) as session:
            records = session.execute_read(_tx)

        for record in records:
            proxy_income = record["proxy_total_income"] or 0
            asset_count = record["asset_count"]

            severity = AnomalySeverity.CRITICAL if asset_count > 2 else AnomalySeverity.HIGH

            anomalies.append(SurrogateWalletAnomaly(
                code="CONNECTED_LOW_INCOME_LUXURY_OWNER",
                severity=severity,
                title="PoA Recipient with Low Income Owns Multiple Assets",
                description=(
                    f"Official gave PoA to {record['proxy_name']} who has "
                    f"{proxy_income:,.0f} UAH income but owns {asset_count} asset(s)"
                ),
                details={
                    "proxy_rnokpp": record["proxy_rnokpp"],
                    "proxy_name": record["proxy_name"],
                    "proxy_total_income": proxy_income,
                    "asset_count": asset_count,
                    "assets": record["assets"][:5],  # First 5
                },
                official_rnokpp=official_rnokpp,
                proxy_rnokpp=record["proxy_rnokpp"],
                recommendation=(
                    "Verify legitimate source of proxy's assets. "
                    "Investigate if official is beneficial owner of these assets."
                ),
            ))

        return anomalies

    # =========================================================================
    # Alternative Scan: Find All Suspicious Proxies
    # =========================================================================

    def _detect_all_suspicious_proxies(self, limit: int) -> List[SurrogateWalletAnomaly]:
        """
        Find all low-income persons who own assets and have PoA connections
        to officials/PEPs.
        """
        anomalies = []

        def _tx(tx):
            result = tx.run(
                """
                // Find persons with low income who own assets
                MATCH (proxy:Person)-[:OWNS]->(asset:Property)
                OPTIONAL MATCH (proxy)-[:EARNED_INCOME]->(inc:IncomeRecord)
                WITH proxy, asset, sum(inc.income_paid) as total_income
                WHERE total_income < $low_income_threshold
                   OR total_income IS NULL

                // Find connected officials via PoA
                MATCH (poa:PowerOfAttorney)-[:HAS_PROPERTY]->(asset)
                MATCH (poa)-[:HAS_REPRESENTATIVE]->(official:Person)
                WHERE official.rnokpp <> proxy.rnokpp

                RETURN
                    official.rnokpp as official_rnokpp,
                    official.last_name + ' ' + official.first_name + ' ' + coalesce(official.middle_name, '') as official_name,
                    proxy.rnokpp as proxy_rnokpp,
                    proxy.last_name + ' ' + proxy.first_name + ' ' + coalesce(proxy.middle_name, '') as proxy_name,
                    total_income as proxy_income,
                    asset.property_id as asset_id,
                    asset.property_type as asset_type,
                    asset.description as asset_description
                LIMIT $limit
                """,
                low_income_threshold=self.low_income_threshold,
                limit=limit,
            )
            return list(result)

        with self._driver.session(database=self._db) as session:
            records = session.execute_read(_tx)

        for record in records:
            proxy_income = record["proxy_income"] or 0

            anomalies.append(SurrogateWalletAnomaly(
                code="SUSPICIOUS_PROXY_ASSET",
                severity=AnomalySeverity.HIGH,
                title="Low-Income Owner with PoA Link to Official",
                description=(
                    f"{record['proxy_name']} (income: {proxy_income:,.0f} UAH) owns "
                    f"{record['asset_type']} with PoA link to {record['official_name']}"
                ),
                details={
                    "proxy_rnokpp": record["proxy_rnokpp"],
                    "proxy_name": record["proxy_name"],
                    "proxy_income": proxy_income,
                    "official_name": record["official_name"],
                    "asset_id": record["asset_id"],
                    "asset_type": record["asset_type"],
                    "asset_description": record["asset_description"],
                },
                official_rnokpp=record["official_rnokpp"],
                proxy_rnokpp=record["proxy_rnokpp"],
                recommendation=(
                    "Investigate relationship between proxy and official. "
                    "Verify source of funds for asset purchase."
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
        """Get all persons marked as PEP/officials."""
        def _tx(tx):
            # Try to find PEPs first, fall back to all persons with PoA connections
            result = tx.run(
                """
                // Find persons who are grantors or representatives in PoAs
                MATCH (p:Person)
                WHERE (p)-[:HAS_GRANTOR|HAS_REPRESENTATIVE]-(:PowerOfAttorney)
                   OR exists(p.is_pep)
                RETURN DISTINCT p.rnokpp as rnokpp
                LIMIT $limit
                """,
                limit=limit,
            )
            return [dict(r) for r in result]

        with self._driver.session(database=self._db) as session:
            return session.execute_read(_tx)

    def _calculate_risk_score(self, anomalies: List[SurrogateWalletAnomaly]) -> float:
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
