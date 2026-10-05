"""Generate static charts from a DH-COMPASS result JSON file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dh_compass.reporting.charts import generate_all_charts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path, help="path to full_results.json")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    with args.results.open("r", encoding="utf-8") as handle:
        results = json.load(handle)
    generate_all_charts(results, str(args.output_dir or args.results.parent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
