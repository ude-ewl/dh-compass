
"""Street-network acquisition."""
from __future__ import annotations

from hashlib import sha256

from dh_compass.preprocessing.osm_graph_index import (
    ensure_graphml_spatial_index,
    load_graphml_bbox,
    spatial_index_path,
)


def _graphml_bool(value):
    """Read text and numeric boolean encodings used in the local GraphML."""
    if value is None or value is False or value == "None":
        return False
    if value is True:
        return True
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "-1"}:
        return True
    if normalized in {"false", "0", "none", ""}:
        return False
    raise ValueError(f"Invalid boolean value in local street GraphML: {value!r}")


def _load_graphml(path, ox):
    """Load the NRW GraphML without coercing OSM direction tags to booleans."""
    return ox.load_graphml(
        filepath=path,
        edge_dtypes={"oneway": str, "reversed": str},
        graph_dtypes={"consolidated": _graphml_bool, "simplified": _graphml_bool},
    )


def street_network_cache_path(config):
    """Return the cache location scoped to the scenario's execution bbox."""
    bbox = ",".join(
        f"{float(value):.6f}"
        for value in config.scenario.bbox
    )
    suffix = sha256(bbox.encode("ascii")).hexdigest()[:16]
    return config.paths.cache_root / f"street_network_local_{suffix}.graphml"


def download_street_network(config, *, force_refresh: bool = False):
    """Load the street network from the local GraphML file or its derived cache."""
    import osmnx as ox

    if config.scenario.geodata_frame != "bbox":
        raise ValueError(
            f"Unsupported geodata_frame "
            f"{config.scenario.geodata_frame!r}; only 'bbox' is implemented"
        )

    cache_path = street_network_cache_path(config)

    # Reuse the existing cache unless a refresh was explicitly requested.
    if cache_path.is_file() and not force_refresh:
        return _load_graphml(cache_path, ox).to_undirected()

    # The shared spatial index is built from GraphML once. Later bounding boxes
    # query the SQLite RTree and load only nearby edges into memory.
    local_path = config.paths.external_data / "osm" / "driving_network_nrw.graphml"
    if not local_path.is_file():
        raise FileNotFoundError(
            "No local OSM street network found. Place the NRW GraphML file at "
            f"{local_path}. Street networks are loaded from local files; Overpass is disabled."
        )
    print(f"Using local street network: {local_path}")
    index_path = ensure_graphml_spatial_index(
        local_path, spatial_index_path(config.paths.cache_root)
    )
    graph = load_graphml_bbox(index_path, config.scenario.bbox)

    if graph.number_of_nodes() == 0:
        raise RuntimeError("The local street network contains no nodes.")

    if graph.number_of_edges() == 0:
        raise RuntimeError(
            f"The local NRW street network does not cover the configured bbox {config.scenario.bbox}."
        )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(graph, filepath=cache_path)

    return graph.to_undirected()


__all__ = ["download_street_network", "street_network_cache_path"]

