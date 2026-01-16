import argparse
import json
import os
from pathlib import Path

from normalizer.core import LLMNormalizer


def iter_json_files(root_dir: str):
    for dirpath, _, filenames in os.walk(root_dir):
        for name in filenames:
            if name.lower().endswith(".json"):
                yield os.path.join(dirpath, name)


def main(parsed_dir: str, output_dir: str) -> None:
    parsed_dir = os.path.abspath(parsed_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    normalizer = LLMNormalizer()

    print(f"[INFO] Starting normalization.")
    print(f"[INFO] Parsed root: {parsed_dir}")
    print(f"[INFO] Output dir : {output_path}")

    any_files = False

    for file_path in iter_json_files(parsed_dir):
        any_files = True
        rel_path = os.path.relpath(file_path, parsed_dir)
        print(f"\n[INFO] Processing file: {rel_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            print(f"[ERROR] Skipping {rel_path}: could not load JSON ({exc})")
            continue

        if not isinstance(payload, dict):
            print(f"[WARN] Skipping {rel_path}: top-level JSON is not an object")
            continue

        items = payload.get("items", [])
        if not isinstance(items, list):
            print(f"[WARN] Skipping {rel_path}: 'items' key is not a list")
            continue

        if not items:
            print(f"[WARN] Skipping {rel_path}: 'items' list is empty")
            continue

        print(f"[INFO] Found {len(items)} items in {rel_path}")

        # Build a base name for output files derived from relative path
        rel_slug = rel_path.replace(os.sep, "_").rsplit(".json", 1)[0]

        for idx, item in enumerate(items):
            # Try to log some IDs if present
            request_id = None
            if isinstance(item, dict):
                request_id = (
                    item.get("request_id")
                    or item.get("requestId")
                    or item.get("REQUEST_ID")
                )

            print(
                f"[INFO]   Normalizing item {idx} "
                f"(file={rel_path}, request_id={request_id!r})"
            )

            out_filename = f"{rel_slug}_item-{idx}.json"
            out_file = output_path / out_filename

            try:
                normalized = normalizer.normalize(item)
            except Exception as exc:
                print(
                    f"[ERROR]   Error normalizing item {idx} "
                    f"(file={rel_path}, request_id={request_id!r}): {exc}"
                )
                continue

            try:
                with open(out_file, "w", encoding="utf-8") as out_f:
                    json.dump(normalized, out_f, ensure_ascii=False, indent=2)
                print(f"[OK]     Written {out_file}")
            except Exception as exc:
                print(f"[ERROR]   Error writing {out_file}: {exc}")

    if not any_files:
        print(f"[WARN] No JSON files found under {parsed_dir}")

    print("\n[INFO] Normalization run finished.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Normalize all parsed JSON files under a directory (recursively)."
    )
    parser.add_argument(
        "--parsed-dir",
        type=str,
        default="parsed",
        help="Directory containing parsed registry files (will be scanned recursively)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="normalized",
        help="Directory to write normalised JSON results",
    )
    args = parser.parse_args()
    main(args.parsed_dir, args.output_dir)
