"""Street-network acquisition."""

from __future__ import annotations

from hashlib import sha256


def street_network_cache_path(config):
    """Return the cache location scoped to the scenario's execution bbox."""

    bbox = ",".join(f"{float(value):.6f}" for value in config.scenario.bbox)
    suffix = sha256(bbox.encode("ascii")).hexdigest()[:16]
    return config.paths.cache_root / f"street_network_{suffix}.graphml"


def download_street_network(config, *, force_refresh: bool = False):
    """Load the cached OSM street network or download and cache it on demand."""

    import osmnx as ox

    if config.scenario.geodata_frame != "bbox":
        raise ValueError(
            f"Unsupported geodata_frame {config.scenario.geodata_frame!r}; only 'bbox' is implemented"
        )
    cache_path = street_network_cache_path(config)
    if cache_path.is_file() and not force_refresh:
        return ox.load_graphml(filepath=cache_path).to_undirected()

    graph = ox.graph_from_bbox(config.scenario.bbox, network_type="drive")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(graph, filepath=cache_path)
    return graph.to_undirected()


__all__ = ["download_street_network", "street_network_cache_path"]
