"""Candidate connection lookup and network-cost calculations."""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping
from contextlib import nullcontext
from dataclasses import dataclass

import networkx as nx
import pandas as pd

from ..network.routing import find_shortest_path_between_subgraphs
from ..observability.performance import PerformanceTracker
from .context import OptimizationContext
from .run_state import OptimizationRunState


@dataclass(frozen=True)
class ConnectionResult:
    """Shortest path from a candidate subgraph to the connected grid."""

    ids: str | None
    path: list[Hashable] | None
    length: float


@dataclass(frozen=True)
class GridCostResult:
    """Raw network costs used in one candidate decision."""

    grid_cost: float
    pump_cost: float
    connection_length: float
    connection: ConnectionResult | None


class ConnectionEvaluator:
    """Find grid connections and calculate their raw infrastructure costs."""

    def __init__(
        self,
        street_network: nx.Graph,
        subgraph_dict: dict[int, nx.Graph],
        subgraph_attributes_df: pd.DataFrame,
        context: OptimizationContext,
        *,
        performance_tracker: PerformanceTracker | None = None,
    ) -> None:
        self.street_network = street_network
        self.subgraph_dict = subgraph_dict
        self.subgraph_attributes_df = (
            subgraph_attributes_df.set_index("Subgraph ID")
            if "Subgraph ID" in subgraph_attributes_df.columns
            else subgraph_attributes_df
        )
        self.context = context
        self.performance_tracker = performance_tracker

    def _measure(self, name: str):
        if self.performance_tracker is None:
            return nullcontext()
        return self.performance_tracker.measure(name)

    def find_shortest_connection(
        self,
        subgraph_id: int,
        connected_subgraphs: Iterable[int],
    ) -> ConnectionResult:
        """Find the shortest path from ``subgraph_id`` to any connected area."""

        connected = list(connected_subgraphs)
        if not connected:
            return ConnectionResult(ids=None, path=None, length=0.0)

        paths: list[list[Hashable]] = []
        lengths: list[float] = []
        ids: list[str] = []

        with self._measure("find_shortest_path"):
            for connected_id in connected:
                path, length = find_shortest_path_between_subgraphs(
                    self.street_network,
                    self.subgraph_dict,
                    connected_id,
                    subgraph_id,
                )
                if path is not None:
                    paths.append(path)
                    lengths.append(length)
                    ids.append(f"{connected_id}_{subgraph_id}")

        if not paths:
            return ConnectionResult(ids=None, path=None, length=float("inf"))

        shortest_index = min(range(len(lengths)), key=lengths.__getitem__)
        return ConnectionResult(
            ids=ids[shortest_index],
            path=paths[shortest_index],
            length=lengths[shortest_index],
        )

    def find_nearest_candidate(
        self,
        candidates: Iterable[int],
        connected_subgraphs: Iterable[int],
        demand_lookup: Mapping[int, float],
    ) -> tuple[int | None, float]:
        """Find the candidate nearest to the combined connected network."""

        candidate_ids = list(candidates)
        if not candidate_ids:
            return None, float("inf")

        source_nodes: set[Hashable] = set()
        for subgraph_id in connected_subgraphs:
            subgraph = self.subgraph_dict.get(subgraph_id)
            if subgraph:
                source_nodes.update(subgraph.nodes())

        if not source_nodes:
            return candidate_ids[0], 0.0

        try:
            distances = nx.multi_source_dijkstra_path_length(
                self.street_network,
                sources=source_nodes,
                weight="length",
            )
        except nx.NetworkXNoPath:
            return candidate_ids[0], float("inf")

        best_id: int | None = None
        best_distance = float("inf")
        best_demand = -1.0
        for subgraph_id in candidate_ids:
            subgraph = self.subgraph_dict.get(subgraph_id)
            if not subgraph:
                continue
            subgraph_distance = min(
                (distances.get(node, float("inf")) for node in subgraph.nodes()),
                default=float("inf"),
            )
            demand = demand_lookup.get(subgraph_id, 0.0)
            if (subgraph_distance < best_distance) or (
                subgraph_distance == best_distance and demand > best_demand
            ):
                best_distance = subgraph_distance
                best_id = subgraph_id
                best_demand = demand

        return best_id, best_distance

    def get_subgraph_grid_cost(self, subgraph_id: int) -> float:
        """Return distribution, building-connection, and station CAPEX."""

        row = self.subgraph_attributes_df.loc[subgraph_id]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        return float(
            row["Total distribution pipe cost [€]"]
            + row["Total building connection cost [€]"]
            + row["Total transfer station cost [€]"]
        )

    def calculate_grid_cost(
        self,
        subgraph_id: int,
        demand_heat: pd.Series,
        state: OptimizationRunState,
        *,
        is_first: bool,
        connection: ConnectionResult | None = None,
    ) -> GridCostResult:
        """Calculate raw grid and pump costs for one candidate.

        The cumulative pump adjustment and connection-pipeline addition mirror
        the established decision equation.  Annualization is intentionally
        left to :class:`CandidateEvaluator` so this service only handles raw
        infrastructure costs.
        """

        subgraph_grid_cost = self.get_subgraph_grid_cost(subgraph_id)
        grid_peak_load_kw = float(demand_heat.max())
        pump_cost = float(
            self.context.runtime_services.pump_cost_func(grid_peak_load_kw)
        )
        network = self.context.network
        factor = network.infrastructure_cost_factor

        if is_first:
            grid_cost = (subgraph_grid_cost + pump_cost) * factor
            connection_length = 0.0
        else:
            if connection is None:
                connection = self.find_shortest_connection(
                    subgraph_id,
                    state.connected_subgraphs,
                )
            connection_length = connection.length
            old_pump_if = state.pump_cost_cumulative * factor
            new_pump_if = pump_cost * factor
            marginal_if = (
                subgraph_grid_cost
                + connection_length * network.pipeline_cost_per_m
            ) * factor
            grid_cost = (
                state.grid_cost_cumulative
                - old_pump_if
                + new_pump_if
                + marginal_if
            )

        return GridCostResult(
            grid_cost=grid_cost,
            pump_cost=pump_cost,
            connection_length=connection_length,
            connection=connection,
        )


__all__ = [
    "ConnectionEvaluator",
    "ConnectionResult",
    "GridCostResult",
]
