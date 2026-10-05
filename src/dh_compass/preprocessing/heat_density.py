"""Edge-level heat demand and linear heat-density calculations."""

from __future__ import annotations

import networkx as nx


def _edge_records(graph):
    if graph.is_multigraph():
        return graph.edges(keys=True, data=True)
    return ((u, v, 0, data) for u, v, data in graph.edges(data=True))


def _normalise_building_edge(edge, multigraph: bool):
    edge = tuple(edge)
    return edge if multigraph else edge[:2]


def add_edge_heat_demand(buildings, street_network, flh: float):
    """Attach annual demand, peak load, and building counts to street edges."""

    multigraph = street_network.is_multigraph()
    building_edges = buildings["nearest_edge"].map(
        lambda edge: _normalise_building_edge(edge, multigraph)
    )
    edge_heat_demand = buildings.assign(_edge=building_edges).groupby("_edge")[
        "heat_demand"
    ].sum()
    edge_peak_load = edge_heat_demand * 1000 / flh
    nx.set_edge_attributes(street_network, edge_heat_demand.to_dict(), "heat_demand")
    nx.set_edge_attributes(street_network, edge_peak_load.to_dict(), "peak_load")

    for u, v, key, data in _edge_records(street_network):
        heat_demand = data.get("heat_demand", 0.0)
        length = data.get("length", 0.0)
        data["linear_heat_density"] = heat_demand / length if length > 0 else 0.0

    counts = building_edges.value_counts()
    for edge, count in counts.items():
        edge = tuple(edge)
        if multigraph and len(edge) == 3:
            u, v, key = edge
            if street_network.has_edge(u, v, key):
                street_network[u][v][key]["building_count_edge"] = int(count)
            elif street_network.has_edge(v, u, key):
                street_network[v][u][key]["building_count_edge"] = int(count)
        else:
            u, v = edge[:2]
            if street_network.has_edge(u, v):
                street_network[u][v]["building_count_edge"] = int(count)
            elif street_network.has_edge(v, u):
                street_network[v][u]["building_count_edge"] = int(count)
    return street_network


def screen_edges_by_linear_heat_density(street_network, threshold: float):
    """Return a graph containing edges above the configured LHD threshold."""

    if street_network.is_multigraph():
        edges = [
            (u, v, key)
            for u, v, key, data in _edge_records(street_network)
            if data.get("linear_heat_density", 0.0) > threshold
        ]
    else:
        edges = [
            (u, v)
            for u, v, _, data in _edge_records(street_network)
            if data.get("linear_heat_density", 0.0) > threshold
        ]
    return street_network.edge_subgraph(edges).copy()


__all__ = ["add_edge_heat_demand", "screen_edges_by_linear_heat_density"]
