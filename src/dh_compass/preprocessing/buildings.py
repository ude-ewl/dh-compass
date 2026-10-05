"""Building-data loading and building-to-street-edge mapping."""

from __future__ import annotations


def building_column_sources(columns, available, geometry_name=None):
    """Resolve provider names to the existing model fields without changing values."""
    available = set(available)
    geometry_names = {"shape", "geometry", (geometry_name or "").lower()}
    sources = {}
    for column in columns:
        if column.lower() in geometry_names:
            continue
        source = "Nutzflaeche" if column == "NF" and column not in available else column
        if source not in available:
            raise ValueError(f"Building dataset is missing required column: {column}")
        sources[column] = source
    return sources


def load_buildings(config):
    """Load and filter heated buildings for the configured bounding box."""

    import geopandas as gpd
    import pyogrio
    from shapely.geometry import box

    path = config.paths.building_data
    if not path.exists():
        raise FileNotFoundError(
            f"Building dataset not found: {path}. Place external inputs under data/external."
        )
    west, south, east, north = config.scenario.bbox
    bbox_wgs84 = box(west, south, east, north)
    bbox_utm = gpd.GeoSeries([bbox_wgs84], crs=4326).to_crs(25832).total_bounds
    info = pyogrio.read_info(path, layer=config.scenario.building_layer)
    sources = building_column_sources(
        config.scenario.building_columns, info["fields"], info.get("geometry_name")
    )
    buildings = gpd.read_file(
        path,
        layer=config.scenario.building_layer,
        engine="pyogrio",
        # Keep the core install free of the optional PyArrow dependency.
        use_arrow=False,
        columns=list(sources.values()),
        bbox=tuple(bbox_utm),
    )
    buildings = buildings.rename(columns={source: column for column, source in sources.items()})
    buildings = buildings.loc[buildings["beheizt"] != 0].copy()
    return buildings.to_crs(4326), bbox_wgs84


def map_buildings_to_edges(buildings, street_network):
    """Return a copy with the nearest OSM edge stored as ``nearest_edge``."""

    import osmnx as ox

    result = buildings.copy()
    points = result.geometry.representative_point()
    edges = ox.distance.nearest_edges(
        street_network, points.x.to_numpy(), points.y.to_numpy()
    )
    result["nearest_edge"] = [tuple(edge) for edge in edges]
    result["heat_demand"] = result["RW_WW"] / 1000.0
    return result


__all__ = ["building_column_sources", "load_buildings", "map_buildings_to_edges"]
