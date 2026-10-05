"""Repair NRW GDB OBJECTID metadata without changing any feature values."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyogrio

from dh_compass.preprocessing.filegdb import repair_nrw_objectid_metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Extracted Warmebedarf_NRW.gdb directory")
    args = parser.parse_args()
    layers = {name for name, _ in pyogrio.list_layers(args.path)}
    if not {"Raumwaermebedarf_ist", "Waermelinien"}.issubset(layers):
        parser.error("This is not the expected NRW heat-demand geodatabase")
    changes = repair_nrw_objectid_metadata(args.path)
    print(json.dumps({"changed_metadata_bytes": len(changes), "changes": changes}, indent=2))
    info = pyogrio.read_info(args.path, layer="Raumwaermebedarf_ist")
    if not len(info["fields"]) or info["features"] <= 0:
        raise RuntimeError("Building layer is still unreadable after the metadata repair")
    # Read actual records as well as catalog metadata.
    sample = pyogrio.read_dataframe(args.path, layer="Raumwaermebedarf_ist", max_features=1)
    print(f"Validated {info['features']:,} buildings, {len(info['fields'])} attributes, {info['crs']}; sample read: {len(sample)}")


if __name__ == "__main__":
    main()
