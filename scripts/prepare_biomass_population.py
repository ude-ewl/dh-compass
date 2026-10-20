"""Prepare a compact, checksum-pinned NRW population dataset without downloads.

Usage: uv run python scripts/prepare_biomass_population.py
The default allocator can also read the original local VG250-EW file directly.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from dh_compass.config import PathConfig, load_config
from dh_compass.resources.biomass import read_biomass_potential, verify_nuts_compatibility
from dh_compass.resources.municipalities import BKG_ATTRIBUTION, file_sha256, load_population


def prepare_population(source: Path, output: Path, biomass_path: Path, scenario: str = "Bio_TWh") -> dict:
    """Validate the complete source and atomically publish a compact preparation."""
    source, output = source.resolve(), output.resolve()
    if source == output:
        raise ValueError("The prepared output must not overwrite the source dataset.")
    population = load_population(source)
    potential = read_biomass_potential(biomass_path)
    verify_nuts_compatibility(potential, population.municipalities, population.regions, scenario)
    output.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        population.municipalities.to_file(staged, layer="municipalities", driver="GPKG", index=False)
        with closing(sqlite3.connect(staged)) as connection:
            population.regions.to_sql("regions", connection, index=False)
            connection.execute(
                "INSERT INTO gpkg_contents (table_name, data_type, identifier, description) VALUES (?, ?, ?, ?)",
                ("regions", "attributes", "regions", "Complete NRW regional population denominators"),
            )
            connection.commit()
        metadata = {
            **population.metadata,
            "prepared_at": now.isoformat(), "source_filename": source.name,
            "source_sha256": file_sha256(source), "sha256": file_sha256(staged),
            "biomass_sha256": file_sha256(biomass_path), "biomass_nuts_vintage": "2013",
            "nuts_compatibility": "NRW classification unchanged 2013–2024; explicit assignments and source representative-point check",
            "nuts_compatibility_reference": "https://ec.europa.eu/eurostat/web/nuts/history",
            "attribution": BKG_ATTRIBUTION.replace("© BKG,", f"© BKG ({now.year}),"),
            "modifications": "Filtered NRW GF=4 municipalities; joined NUTS2 assignments; stored compact municipal and regional tables.",
        }
        staged_manifest = Path(temporary) / "manifest.json"
        staged_manifest.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        staged.replace(output)
        staged_manifest.replace(output.with_suffix(".manifest.json"))
    return metadata


def main() -> None:
    paths = PathConfig.from_project_root(Path(__file__).resolve().parents[1])
    config = load_config(project_root=paths.project_root)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=config.resources.biomass_population_path)
    parser.add_argument("--output", type=Path, default=paths.cache_root / "biomass/municipal_allocation_2024.gpkg")
    args = parser.parse_args()
    # CLI-relative paths are deliberately resolved against the project, not cwd.
    source = args.source if args.source.is_absolute() else paths.project_root / args.source
    output = args.output if args.output.is_absolute() else paths.project_root / args.output
    metadata = prepare_population(source, output, config.resources.biomass_path)
    print(json.dumps({"output": str(output), "municipality_count": metadata["municipality_count"],
                      "sha256": metadata["sha256"]}, indent=2))


if __name__ == "__main__":
    main()
