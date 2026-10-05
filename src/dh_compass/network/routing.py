from collections.abc import Hashable, Iterable, Mapping

import networkx as nx


def create_combined_graph(
    connected_subgraphs: Iterable[int], subgraph_dict: Mapping[int, nx.Graph]
) -> nx.MultiGraph:
    """Combine selected subgraphs into a single MultiGraph."""
    combined_graph = nx.MultiGraph()
    for subgraph_id in connected_subgraphs:
        subgraph = subgraph_dict.get(subgraph_id)
        if subgraph:
            if not isinstance(subgraph, nx.MultiGraph):
                subgraph = nx.MultiGraph(subgraph)
            combined_graph = nx.compose(combined_graph, subgraph)
    return combined_graph


def find_shortest_path_between_subgraphs(
    street_network: nx.Graph,
    subgraph_dict: Mapping[int, nx.Graph],
    subgraph_id_1: int,
    subgraph_id_2: int,
) -> tuple[list[Hashable] | None, float]:
    """Find the shortest path between two subgraphs on the street network.

    Uses multi-source Dijkstra: runs a single Dijkstra from all nodes in
    subgraph_1 simultaneously, then picks the closest node in subgraph_2.
    This replaces the previous O(|S1|*|S2|) pairwise Dijkstra calls with
    a single Dijkstra run.
    """
    subgraph_1 = subgraph_dict.get(subgraph_id_1)
    subgraph_2 = subgraph_dict.get(subgraph_id_2)

    if not subgraph_1 or not subgraph_2:
        return None, float("inf")

    nodes_subgraph_1 = set(subgraph_1.nodes())
    nodes_subgraph_2 = set(subgraph_2.nodes())

    try:
        distances = nx.multi_source_dijkstra_path_length(
            street_network, sources=nodes_subgraph_1, weight="length"
        )
    except nx.NetworkXNoPath:
        return None, float("inf")

    closest_node_2 = None
    shortest_length = float("inf")
    for node in nodes_subgraph_2:
        d = distances.get(node, float("inf"))
        if d < shortest_length:
            shortest_length = d
            closest_node_2 = node

    if closest_node_2 is None:
        return None, float("inf")

    _, shortest_path = nx.multi_source_dijkstra(
        street_network, nodes_subgraph_1, target=closest_node_2, weight="length"
    )

    return shortest_path, shortest_length
