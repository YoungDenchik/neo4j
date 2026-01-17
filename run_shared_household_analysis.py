#!/usr/bin/env python3
"""
CLI script to run shared household detection (Спільний побут).

Detects patterns that may indicate undeclared cohabitation/civil marriage
between officials and non-family members.

Usage:
    # Scan all officials for shared household patterns
    python run_shared_household_analysis.py

    # Scan specific number of officials
    python run_shared_household_analysis.py --limit 50

    # Analyze specific official by RNOKPP
    python run_shared_household_analysis.py --rnokpp 1234567890

    # Output as JSON
    python run_shared_household_analysis.py --json

    # Adjust minimum connection count threshold
    python run_shared_household_analysis.py --min-connections 3
"""
import argparse
import json
import sys
from dataclasses import asdict

from dotenv import load_dotenv

load_dotenv()

from core.neo4j_driver import init_driver, close_driver
from services.shared_household_detector import (
    SharedHouseholdDetector,
    SharedHouseholdAnalysis,
)
from services.income_anomaly_detector import AnomalySeverity


def print_analysis(analysis: SharedHouseholdAnalysis, verbose: bool = False):
    """Pretty print a shared household analysis."""
    print("=" * 80)
    print(f"Official RNOKPP: {analysis.official_rnokpp}")
    if analysis.official_name:
        print(f"Name: {analysis.official_name}")
    print(f"Risk Score: {analysis.risk_score:.0f}/100")
    print(f"Anomalies Found: {len(analysis.anomalies)}")

    summary = analysis.analysis_summary
    print(f"  - PoA to strangers: {summary.get('poa_to_stranger_count', 0)}")
    print(f"  - Multiple PoA connections: {summary.get('multiple_poa_count', 0)}")
    print(f"  - Shared addresses: {summary.get('shared_address_count', 0)}")
    print(f"  - Shared organizations: {summary.get('shared_org_count', 0)}")
    print("-" * 80)

    for i, anomaly in enumerate(analysis.anomalies, 1):
        severity_colors = {
            AnomalySeverity.LOW: "",
            AnomalySeverity.MEDIUM: "⚠️ ",
            AnomalySeverity.HIGH: "🔴 ",
            AnomalySeverity.CRITICAL: "🚨 ",
        }
        prefix = severity_colors.get(anomaly.severity, "")

        print(f"\n{prefix}Anomaly #{i}: [{anomaly.severity.value}] {anomaly.title}")
        print(f"   Code: {anomaly.code}")
        print(f"   {anomaly.description}")
        print(f"   Suspect RNOKPP: {anomaly.suspect_rnokpp}")
        print(f"   Recommendation: {anomaly.recommendation}")

        if verbose:
            print(f"   Details: {json.dumps(anomaly.details, indent=6, default=str)}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Detect shared household patterns (Спільний побут)"
    )
    parser.add_argument(
        "--rnokpp",
        type=str,
        help="Analyze specific official by RNOKPP",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Number of officials to scan (default: 100)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed anomaly information",
    )
    parser.add_argument(
        "--min-risk",
        type=float,
        default=0,
        help="Only show officials with risk score >= this value",
    )

    # Threshold arguments
    parser.add_argument(
        "--min-connections",
        type=int,
        default=2,
        help="Minimum document connections to flag (default: 2)",
    )

    args = parser.parse_args()

    # Initialize Neo4j driver
    init_driver()

    try:
        # Initialize detector with thresholds
        detector = SharedHouseholdDetector(
            min_connection_count=args.min_connections,
        )

        if args.rnokpp:
            # Analyze single official
            print(f"Analyzing official with RNOKPP: {args.rnokpp}")
            analysis = detector.analyze_official(args.rnokpp)

            if args.json:
                print(json.dumps(asdict(analysis), indent=2, default=str))
            else:
                print_analysis(analysis, verbose=args.verbose)

                if not analysis.anomalies:
                    print("✅ No shared household patterns detected for this official.")

        else:
            # Scan multiple officials
            print(f"Scanning top {args.limit} officials for shared household patterns...")
            print(f"Minimum connection count: {args.min_connections}")
            print()

            results = detector.scan_all_officials(limit=args.limit)

            if args.min_risk > 0:
                results = [r for r in results if r.risk_score >= args.min_risk]

            if args.json:
                output = [asdict(r) for r in results]
                print(json.dumps(output, indent=2, default=str))
            else:
                print(f"Found {len(results)} officials with shared household patterns\n")

                if not results:
                    print("✅ No shared household patterns detected.")
                    return

                # Summary table
                print("=" * 80)
                print(f"{'RNOKPP':<15} {'Risk':>6} {'Anomalies':>10} Name")
                print("-" * 80)

                for analysis in results[:50]:  # Top 50
                    name = (analysis.official_name or "")[:35]
                    print(
                        f"{analysis.official_rnokpp:<15} "
                        f"{analysis.risk_score:>5.0f}% "
                        f"{len(analysis.anomalies):>10} "
                        f"{name}"
                    )

                print("=" * 80)

                # Detailed output for top results
                if args.verbose:
                    print("\n\nDETAILED ANALYSIS FOR HIGH-RISK OFFICIALS:\n")
                    for analysis in results[:10]:
                        print_analysis(analysis, verbose=True)

    finally:
        close_driver()


if __name__ == "__main__":
    main()
