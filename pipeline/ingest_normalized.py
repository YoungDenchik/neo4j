# USAGE: python ingest_normalized.py --normalized-dir normalized

import argparse
import os

from pipeline.ingestion_pipeline import IngestionPipeline


def main(normalized_dir: str) -> None:
    normalized_dir = os.path.abspath(normalized_dir)
    print(f"[INFO] Normalized input directory: {normalized_dir}")

    pipeline = IngestionPipeline(normalized_dir=normalized_dir)

    print("[INFO] Starting ingestion into Neo4j...")
    pipeline.run()
    print("[INFO] Ingestion completed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest normalized JSON items into the Neo4j database."
    )
    parser.add_argument(
        "--normalized-dir",
        type=str,
        default="normalized",
        help="Directory containing normalized JSON files.",
    )
    args = parser.parse_args()
    main(args.normalized_dir)
