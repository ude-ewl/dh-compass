"""Explicit state and records for the candidate optimization loop."""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from .connection_evaluator import ConnectionResult

from .result_extraction import ModelSolution


@dataclass(frozen=True)
class IterationRecord:
    """Typed record of one candidate-decision iteration."""

    step: int
    subgraph_id: int
    decision: str
    central_cost_total: float
    previous_central_cost: float
    marginal_central_cost: float
    decentral_cost: float
    grid_cost_raw: float
    connection_length_m: float
    cumulative_connected_ids: list[int]
    connecting_path_nodes: list[Hashable] | None
    distance_to_grid: float | None = None


@dataclass
class OptimizationRunState:
    """Mutable cumulative state shared by candidate-decision services."""

    connected_subgraphs: list[int] = field(default_factory=list)
    connecting_edges_list: list[pd.DataFrame] = field(default_factory=list)
    opt_results_central: dict[int, tuple[float, ModelSolution | None]] = field(
        default_factory=dict
    )
    opt_results_decentral: dict[int, tuple[float, ModelSolution | None]] = field(
        default_factory=dict
    )
    cluster_details: dict[int, dict[int, dict[str, object]]] = field(default_factory=dict)
    grid_cost_cumulative: float = 0.0
    pump_cost_cumulative: float = 0.0
    total_cost_central_cumulative: float = 0.0
    demand_heat_cumulative: pd.Series | float = 0.0
    iteration_history: list[IterationRecord] = field(default_factory=list)

    @property
    def connecting_edges_df(self) -> pd.DataFrame:
        """Build the accumulated connection table without repeated concat."""

        if self.connecting_edges_list:
            return pd.concat(self.connecting_edges_list, ignore_index=True)
        return pd.DataFrame(columns=["ids", "path_length", "path"])

    def accept_candidate(
        self,
        subgraph_id: int,
        *,
        grid_cost: float,
        pump_cost: float,
        total_cost_central: float,
        demand_heat: pd.Series,
        connection: ConnectionResult | None,
    ) -> None:
        """Apply the cumulative state transition for an accepted candidate."""

        self.grid_cost_cumulative = grid_cost
        self.pump_cost_cumulative = pump_cost
        self.total_cost_central_cumulative = total_cost_central
        self.demand_heat_cumulative = demand_heat
        self.connected_subgraphs.append(subgraph_id)

        if connection is not None and getattr(connection, "path", None) is not None:
            self.connecting_edges_list.append(
                pd.DataFrame(
                    [
                        {
                            "ids": connection.ids,
                            "path_length": connection.length,
                            "path": connection.path,
                        }
                    ]
                )
            )

    def reset_iteration_history(self) -> None:
        """Start a new presentation history without discarding cumulative state."""

        self.iteration_history = []


__all__ = ["IterationRecord", "OptimizationRunState"]
