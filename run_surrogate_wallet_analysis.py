#!/usr/bin/env python3
"""
CLI script to run surrogate wallet detection (Гаманець оточення).

Detects patterns where low-income persons own valuable assets that are
controlled by officials through power of attorney.

Usage:
    # Scan all officials for surrogate wallet patterns
    python run_surrogate_wallet_analysis.py

    # Scan specific number of officials
    python run_surrogate_wallet_analysis.py --limit 50

    # Analyze specific official by RNOKPP
    python run_surrogate_wallet_analysis.py --rnokpp 1234567890

    # Scan from proxy perspective (find suspicious asset owners)
    python run_surrogate_wallet_analysis.py --scan-proxies

    # Output as JSON
    python run_surrogate_wallet_analysis.py --json

    # Adjust thresholds
    python run_surrogate_wallet_analysis.py --low-income-threshold 50000
"""
import argparse
import json
import sys
from dataclasses import asdict

from dotenv import load_dotenv

load_dotenv()

from core.neo4j_driver import init_driver, close_driver
from services.surrogate_wallet_detector import (
    SurrogateWalletDetector,
    SurrogateWalletAnalysis,
)
from services.income_anomaly_detector import AnomalySeverity


def print_analysis(analysis: SurrogateWalletAnalysis, verbose: bool = False):
    """Pretty print a surrogate wallet analysis."""
    print("=" * 80)
    print(f"Official RNOKPP: {analysis.official_rnokpp}")
    if analysis.official_name:
        print(f"Name: {analysis.official_name}")
    print(f"Risk Score: {analysis.risk_score:.0f}/100")
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
        print(f"   Proxy RNOKPP: {anomaly.proxy_rnokpp}")
        print(f"   Recommendation: {anomaly.recommendation}")

        if verbose:
            print(f"   Details: {json.dumps(anomaly.details, indent=6, default=str)}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Detect surrogate wallet patterns (Гаманець оточення)"
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
        "--scan-proxies",
        action="store_true",
        help="Scan from proxy perspective (find suspicious asset owners)",
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
        "--low-income-threshold",
        type=float,
        default=100_000.0,
        help="Low income threshold in UAH (default: 100000)",
    )

    args = parser.parse_args()

    # Initialize Neo4j driver
    init_driver()

    try:
        # Initialize detector with thresholds
        detector = SurrogateWalletDetector(
            low_income_threshold=args.low_income_threshold,
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
                    print("✅ No surrogate wallet patterns detected for this official.")

        elif args.scan_proxies:
            # Scan from proxy perspective
            print(f"Scanning for suspicious proxy asset owners (limit: {args.limit})...")
            print(f"Low income threshold: {args.low_income_threshold:,.0f} UAH")
            print()

            results = detector.scan_all_proxies(limit=args.limit)

            if args.min_risk > 0:
                results = [r for r in results if r.risk_score >= args.min_risk]

            if args.json:
                output = [asdict(r) for r in results]
                print(json.dumps(output, indent=2, default=str))
            else:
                print(f"Found {len(results)} officials with surrogate wallet patterns\n")

                if not results:
                    print("✅ No surrogate wallet patterns detected.")
                    return

                print_summary_table(results, args.verbose)

        else:
            # Scan multiple officials
            print(f"Scanning top {args.limit} officials for surrogate wallet patterns...")
            print(f"Low income threshold: {args.low_income_threshold:,.0f} UAH")
            print()

            results = detector.scan_all_officials(limit=args.limit)

            if args.min_risk > 0:
                results = [r for r in results if r.risk_score >= args.min_risk]

            if args.json:
                output = [asdict(r) for r in results]
                print(json.dumps(output, indent=2, default=str))
            else:
                print(f"Found {len(results)} officials with surrogate wallet patterns\n")

                if not results:
                    print("✅ No surrogate wallet patterns detected.")
                    return

                print_summary_table(results, args.verbose)

    finally:
        close_driver()


def print_summary_table(results, verbose):
    """Print summary table of results."""
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
    if verbose:
        print("\n\nDETAILED ANALYSIS FOR HIGH-RISK OFFICIALS:\n")
        for analysis in results[:10]:
            print_analysis(analysis, verbose=True)


if __name__ == "__main__":
    main()
