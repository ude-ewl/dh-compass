"""Convert an authorized local workbook to portable JSON; grants no data rights."""

import argparse
import json
from pathlib import Path

from dh_compass.demand.slp_inputs import COEFFICIENTS, WEEKDAYS, read_slp_tables


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-title", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--source-license", required=True, help="Actual terms, e.g. local-use-only")
    parser.add_argument("--profile", action="append", default=[], metavar="CATEGORY:VARIANT",
                        help="Select explicit profiles without altering or guessing coefficients")
    args = parser.parse_args()
    profiles = tuple(tuple(profile.split(":")) for profile in args.profile)
    if any(len(profile) != 2 for profile in profiles):
        parser.error("--profile must be CATEGORY:VARIANT")
    parameters, factors = read_slp_tables(args.input.resolve(), profiles)
    document = {
        "schema_version": 1,
        "source": {"title": args.source_title, "url": args.source_url, "license": args.source_license},
        "parameters": parameters[["category", "characteristics", *COEFFICIENTS]].to_dict("records"),
        "weekday_factors": factors[["category", *WEEKDAYS]].to_dict("records"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    print("Converted local input. Do not redistribute without permission from its rights holder.")


if __name__ == "__main__":
    main()
