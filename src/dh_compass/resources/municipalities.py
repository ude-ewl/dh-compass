"""Offline, complete NRW population data and unambiguous municipality lookup.

BKG VG250-EW 2024 contains one population-bearing land record (GF=4) per
municipality. Regional denominators are validated before any study-area filter.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from math import isfinite
from pathlib import Path
from typing import Any

POPULATION_DATE = "2024-12-31"
NRW_MUNICIPALITY_COUNTS = {"DEA1": 66, "DEA2": 99, "DEA3": 78, "DEA4": 70, "DEA5": 83}
BKG_SOURCE = (
    "https://gdz.bkg.bund.de/index.php/default/digitale-geodaten/verwaltungsgebiete/"
    "verwaltungsgebiete-1-250-000-mit-einwohnerzahlen-stand-31-12-vg250-ew-31-12.html"
)
BKG_ATTRIBUTION = (
    "© BKG, dl-de/by-2-0; Datenquellen: "
    "https://sgx.geodatenzentrum.de/web_public/gdz/datenquellen/datenquellen_vg_nuts.pdf"
)


class BiomassAllocationError(ValueError):
    """Actionable allocation error, optionally carrying municipality choices."""

    def __init__(self, message: str, *, code: str = "BIOMASS_DATA_INVALID", candidates=None):
        super().__init__(message)
        self.code = code
        self.candidates = candidates or []


@dataclass(frozen=True)
class PopulationData:
    municipalities: Any
    regions: Any
    metadata: dict[str, Any]


def _identity(path: Path) -> tuple[str, int, int]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise BiomassAllocationError(
            f"Biomass input {path.name} is missing. Provide the configured local GeoPackage.",
            code="BIOMASS_INPUT_MISSING",
        )
    stat = path.stat()
    return str(path), stat.st_size, stat.st_mtime_ns


@lru_cache(maxsize=16)
def _sha256(path: str, size: int, mtime_ns: int) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_sha256(path: Path) -> str:
    """Cache the content digest by resolved path, size and modification time."""
    return _sha256(*_identity(path))


def _numeric_population(values, label: str):
    import pandas as pd

    try:
        numeric = pd.to_numeric(values, errors="raise")
    except (ValueError, TypeError) as exc:
        raise BiomassAllocationError(f"{label} population must be numeric.") from exc
    if numeric.isna().any() or not numeric.map(lambda value: isfinite(value) and value >= 0).all():
        raise BiomassAllocationError(f"{label} population must be finite and nonnegative.")
    if not numeric.map(lambda value: float(value).is_integer()).all():
        raise BiomassAllocationError(f"{label} population must contain whole inhabitants.")
    return numeric


def validate_population_frames(municipalities, regions, *, expected_counts=None):
    """Validate normalized frames, including complete regional population sums."""
    import pandas as pd

    required = {"ags", "name", "nuts2", "population", "geometry"}
    if not required.issubset(municipalities.columns):
        raise BiomassAllocationError(f"Municipality fields missing: {sorted(required - set(municipalities.columns))}")
    if not {"nuts2", "population"}.issubset(regions.columns):
        raise BiomassAllocationError("Regional population fields nuts2 and population are required.")
    if municipalities.empty or regions.empty:
        raise BiomassAllocationError("Municipality and regional population data must not be empty.")
    municipal = municipalities.copy()
    regional = regions.copy()
    if not municipal["ags"].map(
        lambda value: isinstance(value, str) and len(value) == 8
        and value.isascii() and value.isdigit()
    ).all() or municipal["ags"].duplicated().any():
        raise BiomassAllocationError("Municipality AGS must be unique eight-digit strings.")
    for frame in (municipal, regional):
        if not frame["nuts2"].map(lambda value: isinstance(value, str) and len(value) == 4).all():
            raise BiomassAllocationError("A valid NUTS2 assignment is required for every population record.")
    if regional["nuts2"].duplicated().any():
        raise BiomassAllocationError("Regional NUTS2 population records must be unique.")
    if municipal.crs is None:
        raise BiomassAllocationError("Municipality geometry CRS is missing.")
    geometry = municipal.geometry
    if geometry.isna().any() or geometry.is_empty.any() or not geometry.is_valid.all():
        raise BiomassAllocationError("Municipality geometry must be nonempty and valid.")
    if not geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise BiomassAllocationError("Municipality geometry must be polygonal.")
    municipal["population"] = _numeric_population(municipal["population"], "Municipal")
    regional["population"] = _numeric_population(regional["population"], "Regional")
    if (regional["population"] <= 0).any():
        raise BiomassAllocationError("Regional population denominators must be positive.")
    if set(municipal["nuts2"]) != set(regional["nuts2"]):
        raise BiomassAllocationError("Municipal and regional NUTS2 population assignments do not match.")
    sums = municipal.groupby("nuts2")["population"].sum().sort_index()
    denominators = regional.set_index("nuts2")["population"].sort_index()
    if not (sums == denominators).all():
        raise BiomassAllocationError(
            "Incomplete or inconsistent regional population: all municipalities must sum to the full regional denominator."
        )
    if expected_counts is not None:
        counts = municipal.groupby("nuts2").size().to_dict()
        if counts != expected_counts:
            raise BiomassAllocationError("Incomplete NRW municipality coverage for the supported population vintage.")
    if not municipal["name"].map(lambda value: isinstance(value, str) and bool(value.strip())).all():
        raise BiomassAllocationError("Municipality names must be present.")
    # Always return independent frames; callers cannot corrupt cached inputs.
    return municipal.reset_index(drop=True), pd.DataFrame(regional).reset_index(drop=True)


@lru_cache(maxsize=4)
def _load_population(path_text: str, size: int, mtime_ns: int, manifest_identity) -> PopulationData:
    import geopandas as gpd
    import pandas as pd

    path = Path(path_text)
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as connection:
        contents = dict(connection.execute("SELECT table_name, description FROM gpkg_contents"))
        if "municipalities" in contents:
            manifest_path = path.with_suffix(".manifest.json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("schema_version") != 1 or manifest.get("population_date") != POPULATION_DATE:
                raise BiomassAllocationError("Unsupported prepared population schema or reference date.")
            if manifest.get("sha256") != file_sha256(path):
                raise BiomassAllocationError("Prepared population checksum does not match its manifest.")
            municipalities = gpd.read_file(path, layer="municipalities")
            regions = pd.read_sql_query("SELECT nuts2, name, population FROM regions", connection)
            metadata = dict(manifest)
        else:
            if contents.get("vg250_gem") != POPULATION_DATE:
                raise BiomassAllocationError(
                    f"Use VG250-EW with population reference date {POPULATION_DATE}; this file has a different or missing vintage."
                )
            municipalities = gpd.read_file(
                path, layer="vg250_gem", where="AGS LIKE '05%' AND GF = 4",
                columns=["AGS", "ARS", "GEN", "EWZ"],
            ).rename(columns={"AGS": "ags", "ARS": "ars", "GEN": "name", "EWZ": "population"})
            assignments = pd.read_sql_query(
                "SELECT ARS_G AS ars, NUTS2_CODE AS nuts2 FROM vgtb_vz_gem WHERE AGS_G LIKE '05%'",
                connection,
            )
            if assignments["ars"].duplicated().any():
                raise BiomassAllocationError("Duplicate municipality-to-NUTS assignments.")
            municipalities = municipalities.merge(assignments, on="ars", how="left", validate="one_to_one")
            regions = pd.read_sql_query(
                "SELECT NUTS AS nuts2, GEN AS name, EWZ AS population FROM vg250_rbz WHERE NUTS LIKE 'DEA%' AND GF = 4",
                connection,
            )
            metadata = {
                "schema_version": 1, "population_date": POPULATION_DATE,
                "boundary_date": POPULATION_DATE, "scope": "NRW", "source_url": BKG_SOURCE,
                "license": "dl-de/by-2-0",
                "attribution": BKG_ATTRIBUTION.replace("© BKG,", f"© BKG ({datetime.now(timezone.utc).year}),"),
                "access_year": datetime.now(timezone.utc).year,
                "modifications": "Filtered NRW GF=4 municipalities; joined official NUTS2 assignments.",
            }
    municipal, regional = validate_population_frames(
        municipalities, regions, expected_counts=NRW_MUNICIPALITY_COUNTS,
    )
    metadata.update({
        "sha256": file_sha256(path), "municipality_count": len(municipal),
        "region_count": len(regional), "crs": municipal.crs.to_string(),
    })
    return PopulationData(municipal, regional, metadata)


def load_population(path: Path | None) -> PopulationData:
    """Read the local BKG input or a checksum-pinned compact preparation."""
    if path is None:
        raise BiomassAllocationError("Configure resources.biomass_population_path.", code="BIOMASS_INPUT_MISSING")
    identity = _identity(path)
    manifest = path.with_suffix(".manifest.json")
    manifest_identity = _identity(manifest) if manifest.exists() else None
    try:
        data = _load_population(*identity, manifest_identity)
    except BiomassAllocationError:
        raise
    except (OSError, sqlite3.Error, ValueError, KeyError) as exc:
        raise BiomassAllocationError(f"Cannot read biomass population dataset: {exc}") from exc
    return PopulationData(data.municipalities.copy(), data.regions.copy(), dict(data.metadata))


def resolve_municipalities(municipalities, bbox, municipality_ags=()):
    """Return full municipality records; touching alone grants no quota."""
    import geopandas as gpd

    if bbox.is_empty or not bbox.is_valid or bbox.geom_type not in {"Polygon", "MultiPolygon"}:
        raise BiomassAllocationError("The study area must be a valid WGS84 polygon.")
    # Intersect in the study's CRS before measuring in metres. Transforming
    # rectangles independently otherwise introduces chord slivers at shared edges.
    study = bbox
    geographic = municipalities.to_crs(4326)
    indices = geographic.sindex.query(study, predicate="intersects")
    candidates = geographic.iloc[indices].copy()
    candidates["overlap_area_m2"] = candidates.geometry.intersection(study).to_crs(25832).area
    candidates = candidates[candidates["overlap_area_m2"] > 1e-6].sort_values("ags")
    choices = [
        {"ags": row.ags, "name": row["name"], "nuts2": row.nuts2,
         "population": int(row.population), "overlap_area_m2": float(row.overlap_area_m2)}
        for _, row in candidates.iterrows()
    ]
    # Boundary layers are internally contiguous. Do not award a full municipal
    # quota to a bbox extending outside supported coverage.
    covered = candidates.geometry.union_all() if hasattr(candidates.geometry, "union_all") else candidates.geometry.unary_union
    uncovered = gpd.GeoSeries([study.difference(covered)], crs=4326).to_crs(25832).area.iloc[0]
    study_area = gpd.GeoSeries([study], crs=4326).to_crs(25832).area.iloc[0]
    if candidates.empty or uncovered > max(1e-6, study_area * 1e-8):
        raise BiomassAllocationError(
            "Municipality data does not fully cover the study area; select an NRW area with complete coverage.",
            code="BIOMASS_AREA_UNCOVERED", candidates=choices,
        )
    requested = tuple(municipality_ags)
    if len(set(requested)) != len(requested):
        raise BiomassAllocationError("Duplicate AGS in biomass municipality selection.")
    if requested:
        if not set(requested).issubset(set(candidates["ags"])):
            raise BiomassAllocationError(
                "Selected biomass AGS must belong to municipalities intersecting the study area.",
                code="BIOMASS_MUNICIPALITY_INVALID", candidates=choices,
            )
        selected = candidates[candidates["ags"].isin(requested)]
    else:
        # Largest share of the study area wins, not largest municipal population.
        # AGS provides a stable tie-breaker independent of source row order.
        selected = candidates.sort_values(
            ["overlap_area_m2", "ags"], ascending=[False, True],
        ).iloc[:1]
    return selected, choices
