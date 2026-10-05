"""Area-weighted biomass potential calculations."""

from __future__ import annotations


def assess_biomass(frame, bbox, scenario: str):
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
    potential = float((clipped[scenario] * clipped["_fraction"]).sum())
    return potential > 0, potential * 1_000_000


__all__ = ["assess_biomass"]
