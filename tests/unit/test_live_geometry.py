import networkx as nx
from shapely.geometry import LineString

from dh_compass.optimization.live_geometry import edge_collection, line_feature


def test_candidate_geometry_preserves_all_parallel_and_curved_edges():
    street = nx.MultiGraph()
    street.add_node(1, x=7.0, y=51.0)
    street.add_node(2, x=7.1, y=51.1)
    street.add_node(3, x=7.2, y=51.2)
    street.add_edge(1, 2, geometry=LineString([(7, 51), (7.05, 51.02), (7.1, 51.1)]))
    street.add_edge(1, 2)
    street.add_edge(2, 3)
    snapshot = edge_collection(street, street, 10, "current")
    assert len(snapshot["features"]) == 3
    assert snapshot["features"][0]["geometry"]["coordinates"] == [
        [7.0, 51.0],
        [7.05, 51.02],
        [7.1, 51.1],
    ]
    assert all(feature["properties"]["decision"] == "current" for feature in snapshot["features"])


def test_missing_or_projected_nodes_are_not_bridged():
    assert line_feature([(7, 51), (None, None), (8, 52)], 10, "connected") is None
    assert line_feature([(700000, 5100000), (700100, 5100100)], 10, "connected") is None
    assert line_feature([(7, 51), (float("nan"), 52)], 10, "connected") is None
