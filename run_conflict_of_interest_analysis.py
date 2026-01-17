import argparse
import json
from dataclasses import asdict

from dotenv import load_dotenv

load_dotenv()

from core.neo4j_driver import init_driver, close_driver
from services.conflict_of_interest_detector import (
    ConflictOfInterestDetector,
    PersonConflictOfInterestAnalysis,
)
from services.income_anomaly_detector import AnomalySeverity


def print_analysis(analysis: PersonConflictOfInterestAnalysis):
    print("=" * 80)
    print(f"RNOKPP: {analysis.person_rnokpp}")
    if analysis.person_name:
        print(f"Name: {analysis.person_name}")
    print(f"Risk Score: {analysis.risk_score:.0f}/100")
    print(f"Anomalies Found: {len(analysis.anomalies)}")
    print("-" * 80)

    severity_icons = {
        AnomalySeverity.LOW: "",
        AnomalySeverity.MEDIUM: "⚠️ ",
        AnomalySeverity.HIGH: "🔴 ",
        AnomalySeverity.CRITICAL: "🚨 ",
    }

    for i, anomaly in enumerate(analysis.anomalies, 1):
        icon = severity_icons.get(anomaly.severity, "")
        print(f"\n{icon}Anomaly #{i}: [{anomaly.severity.value}] {anomaly.title}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Detect conflict-of-interest anomalies"
    )
    parser.add_argument("--rnokpp", type=str, help="Analyze specific person")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    init_driver()

    try:
        detector = ConflictOfInterestDetector()

        if args.rnokpp:
            analysis = detector.analyze_person(args.rnokpp)
            if args.json:
                print(json.dumps(asdict(analysis), indent=2, default=str))
            else:
                print_analysis(analysis)
        else:
            print("Scanning all persons for conflict-of-interest anomalies...\n")

            results = []
            for p in detector._get_all_persons():
                analysis = detector.analyze_person(p["rnokpp"])
                if analysis.anomalies:
                    results.append(analysis)

            if args.json:
                print(json.dumps([asdict(r) for r in results], indent=2, default=str))
            else:
                print(f"Found {len(results)} persons with conflicts\n")
                for a in results[:50]:
                    print_analysis(a)

    finally:
        close_driver()


if __name__ == "__main__":
    main()
