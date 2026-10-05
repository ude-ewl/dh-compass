import geopandas as gpd
import networkx as nx
import pandas as pd
from shapely.geometry import Point

from dh_compass.config import load_default_config
from dh_compass.preprocessing.candidate_areas import build_candidate_areas, order_subgraphs
from dh_compass.preprocessing.heat_density import add_edge_heat_demand


def test_candidate_area_construction_from_tiny_graph(project_root):
    config = load_default_config(project_root=project_root)
    graph = nx.MultiGraph()
    graph.add_edge(1, 2, 0, length=1.0)
    buildings = gpd.GeoDataFrame(
        {
            "nearest_edge": [(1, 2, 0)],
            "RW_WW": [10000.0],
            "GEBAEUDETYP": ["HMF"],
        },
        geometry=[Point(0, 0)],
        crs=4326,
    )
    buildings["heat_demand"] = buildings["RW_WW"] / 1000.0
    add_edge_heat_demand(buildings, graph, config.network.flh)

    def profile(annual_demand_mwh):
        return pd.DataFrame({"load": [annual_demand_mwh * 1000 / 2] * 2})

    lhd, subgraphs, attributes = build_candidate_areas(
        buildings,
        graph,
        config,
        building_profile_generator=profile,
    )

    assert len(subgraphs) == 1
    assert len(lhd.edges) == 1
    assert attributes.loc[0, "Annual Heat Demand [MWh/a]"] == 10.0
    assert order_subgraphs(graph, subgraphs, attributes, "demand_descending") == [1]
