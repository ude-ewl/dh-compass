"""Small, solver-independent geographic snapshots for optimization observers."""

from __future__ import annotations

import math
from collections.abc import Iterable

import networkx as nx


def edge_collection(
    graph: nx.Graph,
    street_network: nx.Graph,
    candidate_id: int,
    decision: str,
) -> dict[str, object]:
    """Preserve every candidate edge, including curved and parallel streets."""
    features = []
    for left, right, attributes in graph.edges(data=True):
        geometry = attributes.get("geometry")
        coordinates = (
            list(geometry.coords)
            if geometry is not None and geometry.geom_type == "LineString"
            else [
                (
                    street_network.nodes.get(node, {}).get("x"),
                    street_network.nodes.get(node, {}).get("y"),
                )
                for node in (left, right)
            ]
        )
        feature = line_feature(coordinates, candidate_id, decision)
        if feature is not None:
            feature["properties"]["linear_heat_density"] = attributes.get("linear_heat_density", 0)
            features.append(feature)
    return {"type": "FeatureCollection", "features": features}


def line_feature(
    coordinates: Iterable[Iterable[object]], candidate_id: int, decision: str
) -> dict[str, object] | None:
    """Reject incomplete/projected geometry instead of bridging missing nodes."""
    points = []
    for coordinate in coordinates:
        x, y, *_ = coordinate
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            return None
        if (
            not math.isfinite(x)
            or not math.isfinite(y)
            or not (-180 <= x <= 180 and -90 <= y <= 90)
        ):
            return None
        points.append([float(x), float(y)])
    if len(points) < 2:
        return None
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": points},
        "properties": {"candidate_id": int(candidate_id), "decision": decision},
    }
