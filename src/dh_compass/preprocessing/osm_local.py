"""Load supplementary NRW OpenStreetMap layers from local GeoPackages."""

from __future__ import annotations


def load_local_osm_layers(config):
    """Load local OSM building and road features intersecting the scenario bbox."""
    import geopandas as gpd

    root = config.paths.external_data / "osm"
    bbox = tuple(float(value) for value in config.scenario.bbox)
    buildings_path = root / "buildings_nrw.gpkg"
    roads_path = root / "roads_nrw.gpkg"
    missing = [path for path in (buildings_path, roads_path) if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Local OSM layer file(s) not found: " + ", ".join(map(str, missing))
        )

    buildings = gpd.read_file(
        buildings_path, layer="buildings_nrw", engine="pyogrio", use_arrow=False,
        bbox=bbox, columns=["building", "name", "building:levels"],
    )
    roads = gpd.read_file(
        roads_path, layer="roads_nrw", engine="pyogrio", use_arrow=False,
        bbox=bbox, columns=["highway", "name", "surface", "length"],
    )
    return buildings, roads


__all__ = ["load_local_osm_layers"]
