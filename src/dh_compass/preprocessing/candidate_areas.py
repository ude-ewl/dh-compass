"""Candidate-area construction from screened heat-density edges."""

from __future__ import annotations

from typing import Callable, Mapping

import networkx as nx
import pandas as pd

from dh_compass.network.costs import build_network_cost_functions
from dh_compass.network.routing import find_shortest_path_between_subgraphs
from dh_compass.preprocessing.heat_density import screen_edges_by_linear_heat_density


def build_candidate_areas(
    buildings,
    street_network,
    config,
    *,
    building_profile_generator: Callable[[float], pd.Series] | None = None,
    cost_functions: Mapping[str, Callable[[float], float]] | None = None,
):
    """Construct LHD components and their optimization attributes.

    This is the extracted, testable equivalent of the candidate-area section of
    the legacy runner.  It mutates neither the input building frame nor the
    street graph beyond reading edge attributes.
    """

    cost_functions = cost_functions or build_network_cost_functions(
        distribution_coefficients=config.network.distribution_pipe_cost_coefficients,
        connection_coefficients=config.network.building_connection_cost_coefficients,
        transfer_station_structure=config.network.transfer_station_cost_structure,
        pump_structure=config.network.pump_cost_structure,
    )
    if building_profile_generator is None:
        def building_profile_generator(demand):
            return pd.DataFrame({"load": [demand * 1000]})
    threshold = config.network.linear_heat_density_threshold
    lhd_graph = screen_edges_by_linear_heat_density(street_network, threshold)

    subgraph_dict: dict[int, nx.Graph] = {}
    records: list[dict] = []
    for component_index, component in enumerate(nx.connected_components(lhd_graph), start=1):
        subgraph = lhd_graph.subgraph(component).copy()
        subgraph_dict[component_index] = subgraph
        edges = list(subgraph.edges(data=True))
        total_length = sum(float(data.get("length", 0.0)) for _, _, data in edges)
        if config.scenario.demand_aggregation == "legacy_mean_lhd":
            densities = [float(data.get("linear_heat_density", 0.0)) for _, _, data in edges]
            annual_demand = (sum(densities) / len(densities) * total_length) if densities else 0.0
        else:
            annual_demand = sum(float(data.get("heat_demand", 0.0)) for _, _, data in edges)
        average_lhd = annual_demand / total_length if total_length else 0.0
        building_count = sum(
            int(data.get("building_count_edge", 0)) for _, _, data in edges
        )
        peak_cost = sum(
            cost_functions["distribution_pipe_cost_func"](float(data.get("peak_load", 0.0)))
            * float(data.get("length", 0.0))
            for _, _, data in edges
        )
        records.append(
            {
                "Subgraph ID": component_index,
                "Total network length [m]": total_length,
                "Average Linear Heat Density [MWh/m/a]": average_lhd,
                "Annual Heat Demand [MWh/a]": annual_demand,
                "Total building count": building_count,
                "Building heat demand [MWh/a]": annual_demand / building_count if building_count else 0.0,
                "Total distribution pipe cost [€]": peak_cost,
                "Total building connection cost [€]": 0.0,
                "Total transfer station cost [€]": 0.0,
            }
        )

    attributes = pd.DataFrame(records)
    if attributes.empty:
        attributes = pd.DataFrame(
            columns=[
                "Subgraph ID", "Total network length [m]",
                "Average Linear Heat Density [MWh/m/a]", "Annual Heat Demand [MWh/a]",
                "Total building count", "Building heat demand [MWh/a]",
                "Total distribution pipe cost [€]", "Total building connection cost [€]",
                "Total transfer station cost [€]", "Building Annual Demands [MWh/a]",
                "Building Types", "Load Profile", "Peak Load [MW]",
            ]
        )
        return lhd_graph, subgraph_dict, attributes

    edge_to_subgraph: dict[tuple, int] = {}
    for subgraph_id, subgraph in subgraph_dict.items():
        if subgraph.is_multigraph():
            edge_iterator = subgraph.edges(keys=True)
        else:
            edge_iterator = ((u, v, 0) for u, v in subgraph.edges())
        for u, v, key in edge_iterator:
            edge_to_subgraph[(u, v, key)] = subgraph_id
            edge_to_subgraph[(v, u, key)] = subgraph_id
            if not subgraph.is_multigraph():
                edge_to_subgraph[(u, v)] = subgraph_id
                edge_to_subgraph[(v, u)] = subgraph_id

    enriched_buildings = buildings.copy()
    enriched_buildings["subgraph_id"] = enriched_buildings["nearest_edge"].map(
        lambda edge: edge_to_subgraph.get(tuple(edge))
    )
    flh = config.network.flh
    enriched_buildings["building_peak_load_kw"] = enriched_buildings["heat_demand"] / flh * 1000
    enriched_buildings["transfer_station_cost"] = enriched_buildings["building_peak_load_kw"].map(
        cost_functions["transfer_station_cost_func"]
    )
    enriched_buildings["building_connection_cost"] = enriched_buildings["building_peak_load_kw"].map(
        cost_functions["building_connection_cost_func"]
    )
    transfer_costs = enriched_buildings.groupby("subgraph_id")["transfer_station_cost"].sum()
    connection_costs = enriched_buildings.groupby("subgraph_id")["building_connection_cost"].sum()
    for row_index, row in attributes.iterrows():
        subgraph_id = row["Subgraph ID"]
        attributes.at[row_index, "Total transfer station cost [€]"] = float(
            transfer_costs.get(subgraph_id, 0.0)
        )
        attributes.at[row_index, "Total building connection cost [€]"] = float(
            connection_costs.get(subgraph_id, 0.0)
        )

    demands = enriched_buildings.groupby("subgraph_id")["heat_demand"].apply(list)
    types = enriched_buildings.groupby("subgraph_id")["GEBAEUDETYP"].apply(
        lambda values: [str(value) if pd.notna(value) else "Unknown" for value in values]
    )
    attributes = attributes.merge(
        demands.rename("Building Annual Demands [MWh/a]"),
        left_on="Subgraph ID", right_index=True, how="left",
    )
    attributes = attributes.merge(
        types.rename("Building Types"),
        left_on="Subgraph ID", right_index=True, how="left",
    )
    attributes["Building Annual Demands [MWh/a]"] = attributes[
        "Building Annual Demands [MWh/a]"
    ].map(lambda value: value if isinstance(value, list) else [])
    attributes["Building Types"] = attributes["Building Types"].map(
        lambda value: value if isinstance(value, list) else []
    )
    def _profile_for(demand):
        profile = building_profile_generator(float(demand))
        if isinstance(profile, dict) and "load" in profile:
            profile = profile["load"]
        if isinstance(profile, pd.Series):
            return pd.DataFrame({"load": profile})
        return profile

    attributes["Load Profile"] = attributes["Annual Heat Demand [MWh/a]"].map(_profile_for)
    # The generator used by the package returns a Series.  A DataFrame with a
    # ``load`` column is also accepted for notebook/test adapters.
    attributes["Peak Load [MW]"] = attributes["Load Profile"].map(
        lambda profile: float(
            (profile["load"] if isinstance(profile, pd.DataFrame) else profile).max()
        ) / 1000
    )
    return lhd_graph, subgraph_dict, attributes


def order_subgraphs(
    street_network,
    subgraph_dict,
    subgraph_attributes_df: pd.DataFrame,
    strategy: str,
) -> list[int]:
    """Return candidate IDs using one of the documented ordering strategies."""

    if subgraph_attributes_df.empty:
        return []
    by_demand = subgraph_attributes_df.sort_values(
        by="Annual Heat Demand [MWh/a]", ascending=False
    )["Subgraph ID"].tolist()
    if strategy == "demand_descending":
        return by_demand
    if strategy == "distance_greedy":
        return by_demand  # the optimizer computes the dynamic order at runtime
    if strategy != "distance_ascending":
        raise ValueError(f"Unknown subgraph ordering strategy: {strategy}")

    anchor = by_demand[0]
    distances: dict[int, float] = {}
    for subgraph_id in by_demand:
        if subgraph_id == anchor:
            distances[subgraph_id] = 0.0
        else:
            _, distance = find_shortest_path_between_subgraphs(
                street_network, subgraph_dict, anchor, subgraph_id
            )
            distances[subgraph_id] = distance
    return sorted(by_demand, key=lambda subgraph_id: distances[subgraph_id])


__all__ = ["build_candidate_areas", "order_subgraphs"]
