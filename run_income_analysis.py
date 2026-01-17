#!/usr/bin/env python3
"""
CLI script to run income anomaly detection.

Usage:
    # Scan all persons (top 100 by income)
    python run_income_analysis.py

    # Scan specific number of persons
    python run_income_analysis.py --limit 500

    # Analyze specific person by RNOKPP
    python run_income_analysis.py --rnokpp 1234567890

    # Output as JSON
    python run_income_analysis.py --json

    # Adjust thresholds
    python run_income_analysis.py --concentration-threshold 200000 --spike-multiplier 5.0
"""
import argparse
import json
import sys
from dataclasses import asdict

from dotenv import load_dotenv

load_dotenv()

from core.neo4j_driver import init_driver, close_driver
from services.income_anomaly_detector import (
    IncomeAnomalyDetector,
    PersonIncomeAnalysis,
    AnomalySeverity,
)


def print_analysis(analysis: PersonIncomeAnalysis, verbose: bool = False):
    """Pretty print a person's income analysis."""
    print("=" * 80)
    print(f"RNOKPP: {analysis.person_rnokpp}")
    if analysis.person_name:
        print(f"Name: {analysis.person_name}")
    print(f"Risk Score: {analysis.risk_score:.0f}/100")
    print(f"Total Income: {analysis.total_income:,.0f} UAH")
    print(f"Total Tax Paid: {analysis.total_tax_paid:,.0f} UAH")
    print(f"Anomalies Found: {len(analysis.anomalies)}")
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
        print(f"   Recommendation: {anomaly.recommendation}")

        if verbose:
            print(f"   Details: {json.dumps(anomaly.details, indent=6, default=str)}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Detect income anomalies for AML/tax compliance analysis"
    )
    parser.add_argument(
        "--rnokpp",
        type=str,
        help="Analyze specific person by RNOKPP",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Number of persons to scan (default: 100)",
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
        help="Only show persons with risk score >= this value",
    )

    # Threshold arguments
    parser.add_argument(
        "--mismatch-threshold",
        type=float,
        default=1000.0,
        help="Income mismatch threshold in UAH (default: 1000)",
    )
    parser.add_argument(
        "--concentration-threshold",
        type=float,
        default=100_000.0,
        help="Concentrated income threshold in UAH (default: 100000)",
    )
    parser.add_argument(
        "--unusual-category-threshold",
        type=float,
        default=50_000.0,
        help="Unusual category threshold in UAH (default: 50000)",
    )
    parser.add_argument(
        "--spike-multiplier",
        type=float,
        default=3.0,
        help="Income spike multiplier (default: 3.0x average)",
    )

    args = parser.parse_args()

    # Initialize Neo4j driver
    init_driver()

    try:
        # Initialize detector with thresholds
        detector = IncomeAnomalyDetector(
            income_mismatch_threshold=args.mismatch_threshold,
            concentration_threshold=args.concentration_threshold,
            unusual_category_threshold=args.unusual_category_threshold,
            spike_multiplier=args.spike_multiplier,
        )

        if args.rnokpp:
            # Analyze single person
            print(f"Analyzing person with RNOKPP: {args.rnokpp}")
            analysis = detector.analyze_person(args.rnokpp)

            if args.json:
                print(json.dumps(asdict(analysis), indent=2, default=str))
            else:
                print_analysis(analysis, verbose=args.verbose)

                if not analysis.anomalies:
                    print("✅ No anomalies detected for this person.")
        else:
            # Scan multiple persons
            print(f"Scanning top {args.limit} persons by income for anomalies...")
            print(f"Thresholds: mismatch={args.mismatch_threshold:,.0f}, "
                  f"concentration={args.concentration_threshold:,.0f}, "
                  f"unusual={args.unusual_category_threshold:,.0f}, "
                  f"spike={args.spike_multiplier}x")
            print()

            results = detector.scan_all_persons(limit=args.limit)

            # Filter by min risk score
            if args.min_risk > 0:
                results = [r for r in results if r.risk_score >= args.min_risk]

            if args.json:
                output = [asdict(r) for r in results]
                print(json.dumps(output, indent=2, default=str))
            else:
                print(f"Found {len(results)} persons with anomalies\n")

                if not results:
                    print("✅ No anomalies detected in the scanned population.")
                    return

                # Summary table
                print("=" * 80)
                print(f"{'RNOKPP':<15} {'Risk':>6} {'Anomalies':>10} {'Total Income':>15} Name")
                print("-" * 80)

                for analysis in results[:50]:  # Top 50
                    name = (analysis.person_name or "")[:30]
                    print(
                        f"{analysis.person_rnokpp:<15} "
                        f"{analysis.risk_score:>5.0f}% "
                        f"{len(analysis.anomalies):>10} "
                        f"{analysis.total_income:>14,.0f} "
                        f"{name}"
                    )

                print("=" * 80)

                # Detailed output for top results
                if args.verbose:
                    print("\n\nDETAILED ANALYSIS FOR HIGH-RISK PERSONS:\n")
                    for analysis in results[:10]:
                        print_analysis(analysis, verbose=True)

    finally:
        close_driver()


if __name__ == "__main__":
    main()
