"""Annual biomass *fuel* budgets: municipal population or legacy area weighting.

Bio_TWh already contains the source's 50% district-heating availability share.
Independent calculations never reserve or consume another study's budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import isfinite
from pathlib import Path
from typing import Any

from .municipalities import (
    BiomassAllocationError,
    _identity,
    file_sha256,
    load_population,
    resolve_municipalities,
    validate_population_frames,
)


@dataclass(frozen=True)
class BiomassAssessment:
    limit_mwh: float
    metadata: dict[str, Any]

    @property
    def available(self) -> bool:
        return self.limit_mwh > 0


def _fraction(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not 0 <= value <= 1:
        raise BiomassAllocationError("Biomass budget fraction must be finite and in [0, 1].")
    return float(value)


def _regional_potentials(frame, scenario: str):
    import pandas as pd

    if not {"NUTS_2", scenario}.issubset(frame.columns):
        raise BiomassAllocationError(f"Biomass fields NUTS_2 and {scenario} are required.")
    if frame["NUTS_2"].duplicated().any():
        raise BiomassAllocationError("Biomass NUTS2 records must be unique.")
    return pd.Series(frame[scenario].to_numpy(), index=frame["NUTS_2"])


def _potential(value, nuts2: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise BiomassAllocationError(f"Biomass potential for {nuts2} is missing or invalid.") from exc
    if not isfinite(result) or result < 0:
        raise BiomassAllocationError(f"Biomass potential for {nuts2} must be finite and nonnegative.")
    return result


def allocate_biomass_population(
    frame, municipalities, regions, bbox, scenario: str,
    *, municipality_ags=(), budget_fraction: float = 1.0,
) -> BiomassAssessment:
    """Allocate complete municipality shares, never clipped population shares."""
    fraction = _fraction(budget_fraction)
    municipal, regional = validate_population_frames(municipalities, regions)
    selected, candidates = resolve_municipalities(municipal, bbox, municipality_ags)
    potentials = _regional_potentials(frame, scenario)
    denominators = regional.set_index("nuts2")["population"]
    breakdown = []
    for _, row in selected.iterrows():
        if row.nuts2 not in potentials.index:
            raise BiomassAllocationError(f"No biomass potential for municipality NUTS2 {row.nuts2}.")
        potential = _potential(potentials.loc[row.nuts2], row.nuts2)
        denominator = float(denominators.loc[row.nuts2])
        share = float(row.population) / denominator
        budget = potential * 1_000_000 * share
        breakdown.append({
            "ags": row.ags, "name": row["name"], "nuts2": row.nuts2,
            "population": int(row.population), "region_population": int(denominator),
            "population_share": share, "regional_potential_twh": potential,
            "municipal_budget_mwh": budget, "allocated_fuel_mwh": budget * fraction,
        })
    limit = sum(item["allocated_fuel_mwh"] for item in breakdown)
    if not isfinite(limit):
        raise BiomassAllocationError("Allocated biomass fuel budget is not finite.")
    return BiomassAssessment(limit, {
        "method": "municipality_population", "energy_basis": "fuel", "unit": "MWh/a",
        "scenario_column": scenario, "budget_fraction": fraction,
        "fuel_budget_mwh": limit, "municipalities": breakdown,
        "municipality_selection": "explicit_ags" if municipality_ags else "largest_overlap",
        "municipality_candidates": candidates, "source_dh_availability_fraction": 0.5 if scenario == "Bio_TWh" else None,
        "independent_studies_are_not_reservations": True,
    })


def assess_biomass(frame, bbox, scenario: str):
    """Legacy selected-area allocation; kept for reproducibility and sensitivity."""
    import geopandas as gpd

    projected = frame.to_crs(25832)
    clipped = gpd.overlay(
        projected,
        gpd.GeoDataFrame(geometry=[bbox], crs=4326).to_crs(25832),
        how="intersection",
    )
    if clipped.empty:
        return False, 0.0
    projected = projected.copy()
    projected["_area"] = projected.geometry.area
    clipped["_area"] = clipped.geometry.area
    if "NUTS_2" in projected and "NUTS_2" in clipped:
        areas = projected.set_index("NUTS_2")["_area"]
        clipped["_fraction"] = clipped.apply(
            lambda row: row["_area"] / areas.get(row["NUTS_2"], row["_area"]), axis=1
        )
    else:
        clipped["_fraction"] = 1.0
    for value in clipped[scenario]:
        _potential(value, "selected area")
    potential = float((clipped[scenario] * clipped["_fraction"]).sum())
    return potential > 0, potential * 1_000_000


@lru_cache(maxsize=4)
def _read_potential(path: str, size: int, mtime_ns: int):
    import geopandas as gpd

    return gpd.read_file(path)


def read_biomass_potential(path: Path):
    try:
        frame = _read_potential(*_identity(path))
        if frame.crs is None:
            raise BiomassAllocationError("Biomass potential geometry CRS is missing.")
        return frame.copy()
    except BiomassAllocationError:
        raise
    except (OSError, ValueError) as exc:
        raise BiomassAllocationError(f"Cannot read biomass potential: {exc}") from exc


def verify_nuts_compatibility(frame, municipalities, regions, scenario: str) -> None:
    """Check administrative codes against the supplied NUTS2013 source geometry.

    This is a representative-point consistency check, not population/area
    interpolation. Municipality shares always use their explicit NUTS2 code.
    """
    potentials = _regional_potentials(frame, scenario)
    if frame.crs is None:
        raise BiomassAllocationError("Biomass potential geometry CRS is missing.")
    projected = frame.to_crs(municipalities.crs).set_index("NUTS_2")
    for nuts2 in regions["nuts2"]:
        if nuts2 not in potentials.index:
            raise BiomassAllocationError(f"Biomass source lacks NRW region {nuts2}.")
        _potential(potentials.loc[nuts2], nuts2)
        geometry = projected.loc[nuts2].geometry
        if geometry is None or geometry.is_empty or not geometry.is_valid:
            raise BiomassAllocationError(f"Invalid biomass NUTS geometry for {nuts2}.")
        points = municipalities[municipalities["nuts2"] == nuts2].geometry.representative_point()
        if not points.map(geometry.covers).all():
            raise BiomassAllocationError(
                f"Municipality NUTS2 assignments disagree with source NUTS geography for {nuts2}."
            )


def assess_configured_biomass(resource_config, bbox) -> BiomassAssessment:
    """Canonical file-loading boundary used by the CLI and web preflight."""
    fraction = _fraction(resource_config.biomass_budget_fraction)
    frame = read_biomass_potential(resource_config.biomass_path)
    method = resource_config.biomass_allocation_method
    if method == "area":
        _, limit = assess_biomass(frame, bbox, resource_config.biomass_scenario)
        result = BiomassAssessment(limit * fraction, {
            "method": "area", "energy_basis": "fuel", "unit": "MWh/a",
            "budget_fraction": fraction, "fuel_budget_mwh": limit * fraction,
            "scenario_column": resource_config.biomass_scenario,
        })
    elif method == "municipality_population":
        population = load_population(resource_config.biomass_population_path)
        verify_nuts_compatibility(frame, population.municipalities, population.regions, resource_config.biomass_scenario)
        result = allocate_biomass_population(
            frame, population.municipalities, population.regions, bbox,
            resource_config.biomass_scenario,
            municipality_ags=resource_config.biomass_municipality_ags,
            budget_fraction=fraction,
        )
        result.metadata.update({
            "population_data": population.metadata,
            "population_date": population.metadata["population_date"],
            "biomass_nuts_vintage": "2013",
            "nuts_compatibility": "NRW classification unchanged 2013–2024; explicit assignments and source representative-point check",
            "nuts_compatibility_reference": "https://ec.europa.eu/eurostat/web/nuts/history",
        })
    else:
        raise BiomassAllocationError(f"Unknown biomass allocation method: {method}.")
    result.metadata["potential_sha256"] = file_sha256(resource_config.biomass_path)
    return result


__all__ = [
    "BiomassAllocationError", "BiomassAssessment", "allocate_biomass_population",
    "assess_biomass", "assess_configured_biomass",
]
