"""Compare two local building datasets with the production loader, without changing defaults."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pyogrio
from pyproj import Transformer

from dh_compass.config import load_config
from dh_compass.preprocessing.buildings import building_column_sources, load_buildings

ROOT = Path(__file__).resolve().parents[1]


def inspect_dataset(path, config):
    info = pyogrio.read_info(path, layer=config.scenario.building_layer)
    report = {
        "path": path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name,
        "layer": info["layer_name"],
        "crs": info["crs"],
        "reported_feature_count": info["features"],
        "fields": info["fields"].tolist(),
        "missing_configured_attributes": sorted(
            set(config.scenario.building_columns) - {"Shape"} - set(info["fields"])
        ),
    }
    try:
        report["resolved_column_mapping"] = building_column_sources(
            config.scenario.building_columns, info["fields"], info.get("geometry_name")
        )
        report["missing_configured_attributes"] = []
        buildings, _ = load_buildings(
            replace(config, paths=config.paths.with_overrides({"building_data": path}))
        )
        report.update(
            status="loaded",
            heated_buildings=len(buildings),
            annual_heat_demand_mwh=float(buildings["RW_WW"].sum() / 1000),
            invalid_geometries=int((~buildings.geometry.is_valid).sum()),
        )
        return report, buildings
    except Exception as exc:
        # Keep diagnostics portable: do not emit GDAL build-machine or user paths.
        report.update(status="failed", error_type=type(exc).__name__)
        return report, None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, default=ROOT / "data/external/Warmebedarf_NRW.gdb")
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--bbox", type=float, nargs=4, default=[8.795, 52.195, 8.800, 52.200])
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/research/nrw-building-comparison.json")
    args = parser.parse_args()
    config = load_config(project_root=ROOT)
    config = replace(config, scenario=replace(config.scenario, bbox=tuple(args.bbox)))
    old_report, old = inspect_dataset(args.old.resolve(), config)
    new_report, new = inspect_dataset(args.new.resolve(), config)
    result = {"bbox_wgs84": args.bbox, "gdal_version": pyogrio.__gdal_version_string__,
              "old": old_report, "new": new_report}
    if old is not None and new is not None:
        old = old.assign(geometry_wkb=old.geometry.to_wkb(hex=True)).drop(columns="geometry")
        new = new.assign(geometry_wkb=new.geometry.to_wkb(hex=True)).drop(columns="geometry")
        keys = ["geometry_wkb", *sorted(set(old.columns) - {"geometry_wkb"})]
        old = old.reindex(columns=keys).sort_values(keys).reset_index(drop=True)
        new = new.reindex(columns=keys).sort_values(keys).reset_index(drop=True)
        try:
            pd.testing.assert_frame_equal(
                old, new, check_exact=True, check_dtype=False,
            )
            result["comparison"] = "All selected attributes and geometry coordinates match exactly."
        except AssertionError:
            result["comparison"] = "Differences found in selected attributes or geometries."
        if len(old) == len(new):
            result["different_values_per_column"] = {
                column: int((~(old[column].eq(new[column])
                               | (old[column].isna() & new[column].isna()))).sum())
                for column in keys
            }
        result["heat_demand_difference_mwh"] = (
            new_report["annual_heat_demand_mwh"] - old_report["annual_heat_demand_mwh"]
        )
    else:
        result["comparison"] = "Numerical comparison unavailable because a production load failed."
    # A readable provider layer offers a separate cross-check, not a substitute
    # for the building comparison. Intersecting lines can extend outside the bbox.
    transform = Transformer.from_crs(4326, 25832, always_xy=True)
    bounds = transform.transform_bounds(*args.bbox)
    streets = [pyogrio.read_dataframe(path, layer="Waermelinien", bbox=bounds)
               for path in (args.old.resolve(), args.new.resolve())]
    comparable = [frame.assign(geometry_wkb=frame.geometry.to_wkb(hex=True))
                  .drop(columns="geometry").sort_values("WLD_ID").reset_index(drop=True)
                  for frame in streets]
    identical = True
    try:
        pd.testing.assert_frame_equal(comparable[0], comparable[1], check_exact=True)
    except AssertionError:
        identical = False
    result["supplementary_heat_lines"] = {
        "old_rows": len(streets[0]), "new_rows": len(streets[1]),
        "all_attributes_and_geometries_exactly_equal": identical,
        "old_rw_ww_mwh": float(streets[0]["RW_WW"].sum() / 1000),
        "new_rw_ww_mwh": float(streets[1]["RW_WW"].sum() / 1000),
        "note": "Heat lines are not the building input; this does not establish building equality.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
