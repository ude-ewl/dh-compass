"""Location-dependent heat-resource availability assessment."""

from __future__ import annotations

from pathlib import Path

from dh_compass.config import ResourceAvailability

from .biomass import assess_configured_biomass


def _read(path: Path, *, crs: int | None = None):
    import geopandas as gpd

    frame = gpd.read_file(path)
    return frame.to_crs(epsg=crs) if crs is not None else frame


def assess_heat_resources(config, bbox_wgs84) -> ResourceAvailability:
    """Read configured potential layers and calculate limits inside ``bbox``."""

    resource_config = config.resources
    enabled = set(config.scenario.enabled_resources)
    values: dict[str, object] = {}

    if "industrial_excess_heat" in enabled and resource_config.industrial_heat_path.exists():
        frame = _read(resource_config.industrial_heat_path, crs=4326)
        selected = frame[frame.geometry.within(bbox_wgs84)]
        values["industrial_eh_available"] = bool(len(selected))
        values["industrial_eh_energy_limit_mwh"] = (
            float(selected[resource_config.industrial_heat_scenario].sum()) * 1000
            if len(selected) else 0.0
        )

    if "biomass" in enabled:
        biomass = assess_configured_biomass(resource_config, bbox_wgs84)
        values["biomass_available"] = biomass.available
        values["biomass_energy_limit_mwh"] = biomass.limit_mwh
        values["biomass_allocation"] = biomass.metadata

    if "waste_to_energy" in enabled and resource_config.waste_to_energy_path.exists():
        frame = _read(resource_config.waste_to_energy_path, crs=4326)
        selected = frame[frame.geometry.within(bbox_wgs84)]
        potential_gwh = (
            float(selected[resource_config.waste_to_energy_scenario].sum()) * 277.778
            if len(selected) else 0.0
        )
        values["wte_available"] = potential_gwh > 0
        values["wte_energy_limit_mwh"] = potential_gwh * 1000

    if "geothermal" in enabled and resource_config.hydrothermal_path.exists():
        frame = _read(resource_config.hydrothermal_path, crs=4326)
        selected = frame[frame.geometry.intersects(bbox_wgs84)]
        potential_twh = (
            float(selected[resource_config.hydrothermal_scenario].sum())
            if len(selected) else 0.0
        )
        values["geothermal_available"] = potential_twh > 0
        values["geothermal_energy_limit_mwh"] = potential_twh * 1_000_000

    if "river_heat_pump" in enabled and resource_config.rivers_lakes_path.exists():
        frame = _read(resource_config.rivers_lakes_path, crs=4326)
        selected = frame[frame.geometry.intersects(bbox_wgs84)]
        values["river_hp_available"] = bool(len(selected))
        values["river_hp_capacity_limit_kw"] = (
            float(selected["Capa in MW"].sum()) * 1000 if len(selected) else 0.0
        )

    if "wwtp_heat_pump" in enabled and resource_config.wwtp_path.exists():
        frame = _read(resource_config.wwtp_path, crs=4326)
        selected = frame[frame.geometry.within(bbox_wgs84)]
        values["wwtp_hp_available"] = bool(len(selected))
        values["wwtp_hp_capacity_limit_kw"] = (
            float(selected["Power in k"].sum()) if len(selected) else 0.0
        )

    return ResourceAvailability(**values)


__all__ = ["assess_heat_resources"]
