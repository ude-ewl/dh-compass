"""Evaluate one candidate subgraph against central and decentralized options."""

from __future__ import annotations

import logging
from contextlib import nullcontext
from dataclasses import dataclass

import pandas as pd

from ..observability.performance import PerformanceTracker
from ..observability.progress import CancellationToken, check_cancellation
from .cluster_solver import ClusterSolver
from .clustering import cluster_buildings_to_typgebaeude
from .connection_evaluator import ConnectionEvaluator, ConnectionResult
from .context import OptimizationContext, OptimizationResult
from .model_runner import ModelRun, ModelRunner
from .run_state import OptimizationRunState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CandidateEvaluation:
    """All outputs needed by the loop after evaluating one candidate."""

    result: OptimizationResult
    cluster_details: dict[int, dict[str, object]]
    demand_heat: pd.Series
    connection: ConnectionResult | None
    central_run: ModelRun


class CandidateEvaluator:
    """Compare central and decentralized alternatives for one candidate area."""

    def __init__(
        self,
        context: OptimizationContext,
        subgraph_attributes_df: pd.DataFrame,
        *,
        model_runner: ModelRunner,
        cluster_solver: ClusterSolver,
        connection_evaluator: ConnectionEvaluator,
        annuity_factor_value: float,
        performance_tracker: PerformanceTracker | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        self.context = context
        self.subgraph_attributes_df = (
            subgraph_attributes_df.set_index("Subgraph ID")
            if "Subgraph ID" in subgraph_attributes_df.columns
            else subgraph_attributes_df
        )
        self.model_runner = model_runner
        self.cluster_solver = cluster_solver
        self.connection_evaluator = connection_evaluator
        self.annuity_factor_value = annuity_factor_value
        self.performance_tracker = performance_tracker
        self.cancellation_token = cancellation_token

    def _measure(self, name: str):
        if self.performance_tracker is None:
            return nullcontext()
        return self.performance_tracker.measure(name)

    def evaluate(
        self,
        subgraph_id: int,
        state: OptimizationRunState,
        *,
        is_first: bool,
        max_workers: int | None = None,
    ) -> CandidateEvaluation:
        """Evaluate and, when accepted, apply one candidate state transition."""

        # These checks are deliberately outside the solver call.  A solver that
        # is already optimizing is allowed to finish safely; cancellation is
        # then observed before the next expensive phase or candidate.
        check_cancellation(self.cancellation_token)
        row = self.subgraph_attributes_df.loc[subgraph_id]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        subgraph_load = row["Load Profile"]["load"]
        current_demand_heat = (
            subgraph_load
            if is_first
            else state.demand_heat_cumulative + subgraph_load
        )

        central_run = self.model_runner.run(
            current_demand_heat,
            decentral=False,
            use_gathered_results=True,
            performance_name="central_model_build_and_solve",
        )
        check_cancellation(self.cancellation_token)

        connection = None
        if not is_first:
            connection = self.connection_evaluator.find_shortest_connection(
                subgraph_id,
                state.connected_subgraphs,
            )

        grid_costs = self.connection_evaluator.calculate_grid_cost(
            subgraph_id,
            current_demand_heat,
            state,
            is_first=is_first,
            connection=connection,
        )
        network = self.context.network
        annualized_grid_cost = (
            grid_costs.grid_cost
            - grid_costs.grid_cost * network.residual_value_factor_pipeline
        ) * self.annuity_factor_value
        total_cost_central = central_run.objective_value + annualized_grid_cost

        building_demands = row["Building Annual Demands [MWh/a]"]
        if "Building Types" in self.subgraph_attributes_df.columns:
            building_types = row["Building Types"]
        else:
            building_types = None
        if building_types is None or len(building_types) != len(building_demands):
            building_types = ["Unknown"] * len(building_demands)

        clustering = self.context.clustering
        with self._measure("kmeans_clustering"):
            clusters = cluster_buildings_to_typgebaeude(
                building_demands=building_demands,
                building_types=building_types,
                n_clusters=clustering.n_clusters,
                random_state=clustering.random_state,
            )

        if self.performance_tracker is not None:
            self.performance_tracker.add_optimization_metric(
                f"cluster_count_subgraph_{subgraph_id}",
                len(clusters),
            )

        logger.debug(
            "Solving decentral models for subgraph %s (%s clusters)",
            subgraph_id,
            len(clusters),
        )
        total_cost_decentral, cluster_costs = self.cluster_solver.solve(
            clusters,
            max_workers=max_workers,
        )
        check_cancellation(self.cancellation_token)

        cost_difference = (
            total_cost_central - state.total_cost_central_cumulative
        )
        is_connected = is_first or cost_difference <= total_cost_decentral

        result = OptimizationResult(
            subgraph_id=subgraph_id,
            central_cost=total_cost_central,
            decentral_cost=total_cost_decentral,
            is_connected=is_connected,
            connection_length=grid_costs.connection_length,
            grid_cost=grid_costs.grid_cost,
            pump_cost=grid_costs.pump_cost,
            results_central=central_run.solution,
            results_decentral=None,
            connecting_path_nodes=(
                list(connection.path)
                if connection is not None and connection.path is not None
                else None
            ),
        )

        if is_connected:
            state.accept_candidate(
                subgraph_id,
                grid_cost=grid_costs.grid_cost,
                pump_cost=grid_costs.pump_cost,
                total_cost_central=total_cost_central,
                demand_heat=current_demand_heat,
                connection=connection,
            )

        return CandidateEvaluation(
            result=result,
            cluster_details=cluster_costs,
            demand_heat=current_demand_heat,
            connection=connection,
            central_run=central_run,
        )

    evaluate_candidate = evaluate


__all__ = ["CandidateEvaluation", "CandidateEvaluator"]
