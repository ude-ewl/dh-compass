"""Package the six verified prepared resource files as a separate CC BY 4.0 ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

import pyogrio

ROOT = Path(__file__).resolve().parents[1]
RESOURCE_COLUMNS = {
    "industrial_eh.gpkg": ("EH_95_GWh",),
    "biomass_nuts2(1).gpkg": ("Bio_TWh", "NUTS_2"),
    "wte.gpkg": ("EH100PJ",),
    "hydrothermal_85_nrw.gpkg": ("Energy_TWh",),
    "rivers_lakes.gpkg": ("Capa in MW",),
    "wwtp.gpkg": ("Power in k",),
}
NOTICES = ("README.md", "ATTRIBUTION.md", "PREPARATION.md", "LICENSE-CC-BY-4.0.txt")


def export(destination: Path) -> dict:
    manifest = json.loads((ROOT / "docs/licenses/data-manifest.json").read_text(encoding="utf-8"))
    records = {
        Path(record["local_path"]).name: record
        for record in manifest["datasets"]
        if (record.get("local_path") or "").startswith("data/external/heat_supply_potentials/")
    }
    if set(records) != set(RESOURCE_COLUMNS):
        raise ValueError("Reviewed manifest must contain exactly the six resource inputs")
    payloads = {}
    prepared_records = []
    for filename, required_columns in sorted(RESOURCE_COLUMNS.items()):
        record = dict(records[filename])
        path = ROOT / record["local_path"]
        content = path.read_bytes()
        if record["license"] != "CC-BY-4.0":
            raise ValueError(f"Unexpected data license: {filename}")
        if len(content) != record["size_bytes"] or hashlib.sha256(content).hexdigest() != record["sha256"]:
            raise ValueError(f"Prepared input differs from reviewed manifest: {filename}")
        layers = pyogrio.list_layers(path)
        if len(layers) != 1:
            raise ValueError(f"Expected exactly one layer in {filename}")
        info = pyogrio.read_info(path, layer=layers[0][0])
        if info["crs"] != "EPSG:3035" or not set(required_columns).issubset(info["fields"]):
            raise ValueError(f"Unexpected CRS or resource columns in {filename}")
        record.update(layer=info["layer_name"], crs=info["crs"], feature_count=info["features"],
                      required_columns=list(required_columns), preparation_notes="resource-data-bundle/PREPARATION.md")
        prepared_records.append(record)
        payloads[record["local_path"]] = content
    data_bytes = sum(len(content) for content in payloads.values())
    for name in NOTICES:
        payloads[f"resource-data-bundle/{name}"] = (ROOT / "docs/resource-data-bundle" / name).read_bytes()
    bundle_manifest = {
        "bundle": "DH-COMPASS-resource-data", "version": 1,
        "source_review_date": manifest["review_date"], "data_size_bytes": data_bytes,
        "license": "CC-BY-4.0", "attribution": "resource-data-bundle/ATTRIBUTION.md",
        "datasets": prepared_records,
    }
    payloads["resource-data-bundle/data-manifest.json"] = (
        json.dumps(bundle_manifest, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    payloads["resource-data-bundle/SHA256SUMS.txt"] = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n" for name, content in sorted(payloads.items())
    ).encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(payloads.items()):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, content, compresslevel=9)
    archive_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix + ".sha256").write_text(
        f"{archive_hash}  {destination.name}\n", encoding="utf-8",
    )
    return {"output": destination.name, "resource_files": len(prepared_records),
            "data_bytes": data_bytes, "zip_bytes": destination.stat().st_size, "sha256": archive_hash}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/release/DH-COMPASS-resource-data-v1.zip")
    args = parser.parse_args()
    print(json.dumps(export(args.output.resolve()), indent=2))


if __name__ == "__main__":
    main()
