"""Top-level optimization workflow coordination.

The optimizer keeps the stable public workflow API, while model solving,
cluster execution, connection costs, candidate evaluation, and cumulative state
live in focused services.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence

import networkx as nx
import pandas as pd
from mip import Model

from ..economics.annuity import annuity_factor
from ..observability.performance import PerformanceTracker
from ..observability.progress import (
    CancellationRequested,
    CancellationToken,
    PipelineObserver,
    check_cancellation,
    emit_progress,
)
from .candidate_evaluator import CandidateEvaluator
from .cluster_solver import ClusterSolver
from .connection_evaluator import ConnectionEvaluator
from .context import OptimizationContext, OptimizationResult
from .live_geometry import edge_collection, line_feature
from .model import generate_deterministic_model_mip
from .model_inputs import ModelInputs
from .model_runner import ModelRun, ModelRunner
from .result_extraction import ModelSolution, gather_results_mip
from .run_state import IterationRecord, OptimizationRunState

logger = logging.getLogger(__name__)


def _generate_model(inputs: ModelInputs) -> Model:
    """Build a model through the typed boundary."""

    return generate_deterministic_model_mip(inputs)


class HeatGridOptimizer:
    """Coordinate candidate evaluation while retaining the legacy API."""

    def __init__(
        self,
        context: OptimizationContext,
        street_network: nx.Graph,
        subgraph_dict: dict[int, nx.Graph],
        subgraph_attributes_df: pd.DataFrame,
        performance_tracker: PerformanceTracker | None = None,
        *,
        state: OptimizationRunState | None = None,
        model_runner: ModelRunner | None = None,
        cluster_solver: ClusterSolver | None = None,
        connection_evaluator: ConnectionEvaluator | None = None,
        observer: PipelineObserver | None = None,
        cancellation_token: CancellationToken | None = None,
        highs_central_lp_method: str = "barrier",
        highs_decentral_lp_method: str = "barrier",
        reuse_models: bool = True,
    ):
        self.ctx = context
        self.street_network = street_network
        self.observer = observer
        self.cancellation_token = cancellation_token
        self.subgraph_dict = subgraph_dict
        self.subgraph_attributes_df = subgraph_attributes_df.set_index("Subgraph ID")
        self.perf = performance_tracker or PerformanceTracker()
        self.state = state or OptimizationRunState()
        # Descriptive alias for callers that refer to the workflow state by
        # the role it plays rather than by its short internal name.
        self.run_state = self.state

        economic = self.ctx.economic
        self.annuity_factor_val = annuity_factor(
            economic.interest_rate,
            economic.investment_duration,
        )

        self.model_runner = model_runner or ModelRunner(
            self.ctx,
            model_builder=_generate_model,
            results_gatherer=gather_results_mip,
            performance_tracker=self.perf,
            highs_central_lp_method=highs_central_lp_method,
            highs_decentral_lp_method=highs_decentral_lp_method,
            reuse_models=reuse_models,
        )
        self.cluster_solver = cluster_solver or ClusterSolver(
            self.ctx,
            model_runner=self.model_runner,
            performance_tracker=self.perf,
        )
        self.connection_evaluator = connection_evaluator or ConnectionEvaluator(
            self.street_network,
            self.subgraph_dict,
            self.subgraph_attributes_df,
            self.ctx,
            performance_tracker=self.perf,
        )
        self.candidate_evaluator = CandidateEvaluator(
            self.ctx,
            self.subgraph_attributes_df,
            model_runner=self.model_runner,
            cluster_solver=self.cluster_solver,
            connection_evaluator=self.connection_evaluator,
            annuity_factor_value=self.annuity_factor_val,
            performance_tracker=self.perf,
            cancellation_token=cancellation_token,
        )

    def _check_cancellation(self) -> None:
        check_cancellation(self.cancellation_token)

    def _candidate_started(self, subgraph_id: int, index: int, total: int) -> None:
        self._live_previous_cost = self.state.total_cost_central_cumulative
        geometry = {}
        if self.observer is not None:
            geometry["candidate_geojson"] = edge_collection(
                self.subgraph_dict.get(subgraph_id, nx.Graph()),
                self.street_network,
                subgraph_id,
                "current",
            )
            if index == 0:
                geometry["candidate_network_geojson"] = {
                    "type": "FeatureCollection",
                    "features": [
                        feature
                        for candidate_id, graph in self.subgraph_dict.items()
                        for feature in edge_collection(
                            graph, self.street_network, candidate_id, "pending"
                        )["features"]
                    ],
                }
        emit_progress(
            self.observer,
            "optimization.candidate_started",
            {
                "candidate_id": int(subgraph_id),
                "index": int(index),
                "total_candidates": int(total),
                "completed_candidates": int(index),
                "connected_candidates": len(self.state.connected_subgraphs),
                "rejected_candidates": max(0, index - len(self.state.connected_subgraphs)),
                **geometry,
            },
        )

    def _candidate_completed(
        self,
        result: OptimizationResult,
        *,
        index: int,
        total: int,
        duration_seconds: float,
    ) -> None:
        completed = index + 1
        connected = len(self.state.connected_subgraphs)
        live_geometry = {}
        if self.observer is not None:
            decision = "connected" if result.is_connected else "rejected"
            live_geometry["candidate_geojson"] = edge_collection(
                self.subgraph_dict.get(result.subgraph_id, nx.Graph()),
                self.street_network,
                result.subgraph_id,
                decision,
            )
            path = result.connecting_path_nodes or []
            live_geometry["connecting_path_geojson"] = {
                "type": "FeatureCollection",
                "features": [],
            }
            if result.is_connected and len(path) > 1:
                feature = line_feature(
                    [
                        (
                            self.street_network.nodes.get(node, {}).get("x"),
                            self.street_network.nodes.get(node, {}).get("y"),
                        )
                        for node in path
                    ],
                    result.subgraph_id,
                    decision,
                )
                if feature is not None:
                    live_geometry["connecting_path_geojson"]["features"].append(feature)
        row = self.subgraph_attributes_df.loc[result.subgraph_id]
        connected_demand = (
            float(
                self.subgraph_attributes_df.loc[
                    self.state.connected_subgraphs, "Annual Heat Demand [MWh/a]"
                ].sum()
            )
            if "Annual Heat Demand [MWh/a]" in self.subgraph_attributes_df.columns
            else None
        )
        emit_progress(
            self.observer,
            "optimization.candidate_completed",
            {
                "candidate_id": int(result.subgraph_id),
                "index": int(index),
                "total_candidates": int(total),
                "completed_candidates": completed,
                "connected_candidates": connected,
                "rejected_candidates": completed - connected,
                "decision": "connected" if result.is_connected else "rejected",
                "central_cost": float(result.central_cost),
                "marginal_central_cost": float(
                    result.central_cost - getattr(self, "_live_previous_cost", 0.0)
                ),
                "decentral_cost": float(result.decentral_cost),
                "connection_length_m": float(result.connection_length),
                "duration_seconds": float(duration_seconds),
                "connecting_path_nodes": result.connecting_path_nodes,
                "provisional_geojson": self._provisional_geojson(result),
                "central_cost_total": float(self.state.total_cost_central_cumulative),
                "connected_heat_demand_mwh": connected_demand,
                "annual_heat_demand_mwh": float(row["Annual Heat Demand [MWh/a]"])
                if "Annual Heat Demand [MWh/a]" in row
                else None,
                "buildings": int(row["Total building count"])
                if "Total building count" in row
                else None,
                **live_geometry,
            },
        )

    def _provisional_geojson(self, result: OptimizationResult) -> dict[str, object] | None:
        """Return one WGS84 candidate line for live monitor rendering.

        Street networks downloaded from OSM carry longitude/latitude ``x`` and
        ``y`` node attributes.  A connecting path is most representative after
        the first accepted candidate; otherwise use an edge from the candidate
        subgraph so the monitor can render progress from the first decision.
        """

        node_paths: list[list[object]] = []
        if result.connecting_path_nodes and len(result.connecting_path_nodes) > 1:
            node_paths.append(list(result.connecting_path_nodes))
        else:
            graph = self.subgraph_dict.get(result.subgraph_id)
            if graph is not None:
                node_paths.extend([[left, right] for left, right in graph.edges()])

        for node_path in node_paths:
            coordinates: list[list[float]] = []
            for node_id in node_path:
                attributes = self.street_network.nodes.get(node_id, {})
                x, y = attributes.get("x"), attributes.get("y")
                if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                    coordinates.append([float(x), float(y)])
            if len(coordinates) > 1:
                return {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coordinates},
                    "properties": {
                        "candidate_id": int(result.subgraph_id),
                        "decision": "connected" if result.is_connected else "rejected",
                    },
                }
        return None

    # The properties preserve the state attributes consumed by reporting and
    # existing integrations without duplicating mutable values.
    @property
    def connected_subgraphs(self) -> list[int]:
        return self.state.connected_subgraphs

    @connected_subgraphs.setter
    def connected_subgraphs(self, value: list[int]) -> None:
        self.state.connected_subgraphs = value

    @property
    def connecting_edges_list(self) -> list[pd.DataFrame]:
        return self.state.connecting_edges_list

    @connecting_edges_list.setter
    def connecting_edges_list(self, value: list[pd.DataFrame]) -> None:
        self.state.connecting_edges_list = value

    @property
    def connecting_edges_df(self) -> pd.DataFrame:
        return self.state.connecting_edges_df

    @property
    def opt_results_central(self) -> dict[int, tuple[float, ModelSolution | None]]:
        return self.state.opt_results_central

    @opt_results_central.setter
    def opt_results_central(self, value: dict[int, tuple[float, ModelSolution | None]]) -> None:
        self.state.opt_results_central = value

    @property
    def opt_results_decentral(self) -> dict[int, tuple[float, ModelSolution | None]]:
        return self.state.opt_results_decentral

    @opt_results_decentral.setter
    def opt_results_decentral(self, value: dict[int, tuple[float, ModelSolution | None]]) -> None:
        self.state.opt_results_decentral = value

    @property
    def cluster_details(self) -> dict[int, dict[int, dict[str, object]]]:
        return self.state.cluster_details

    @cluster_details.setter
    def cluster_details(self, value: dict[int, dict[int, dict[str, object]]]) -> None:
        self.state.cluster_details = value

    @property
    def grid_cost_cumulative(self) -> float:
        return self.state.grid_cost_cumulative

    @grid_cost_cumulative.setter
    def grid_cost_cumulative(self, value: float) -> None:
        self.state.grid_cost_cumulative = value

    @property
    def pump_cost_cumulative(self) -> float:
        return self.state.pump_cost_cumulative

    @pump_cost_cumulative.setter
    def pump_cost_cumulative(self, value: float) -> None:
        self.state.pump_cost_cumulative = value

    @property
    def total_cost_central_cumulative(self) -> float:
        return self.state.total_cost_central_cumulative

    @total_cost_central_cumulative.setter
    def total_cost_central_cumulative(self, value: float) -> None:
        self.state.total_cost_central_cumulative = value

    @property
    def demand_heat_cumulative(self) -> pd.Series | float:
        return self.state.demand_heat_cumulative

    @demand_heat_cumulative.setter
    def demand_heat_cumulative(self, value: pd.Series | float) -> None:
        self.state.demand_heat_cumulative = value

    @property
    def iteration_history(self) -> list[IterationRecord]:
        return self.state.iteration_history

    @iteration_history.setter
    def iteration_history(self, value: list[IterationRecord]) -> None:
        self.state.iteration_history = value

    def _find_nearest_candidate(
        self,
        candidates: Sequence[int],
        demand_lookup: Mapping[int, float],
    ) -> tuple[int | None, float]:
        return self.connection_evaluator.find_nearest_candidate(
            candidates,
            self.state.connected_subgraphs,
            demand_lookup,
        )

    def process_subgraph(
        self,
        subgraph_id: int,
        is_first: bool,
        max_workers: int | None = None,
    ) -> OptimizationResult:
        """Evaluate one candidate and apply its state transition if accepted."""

        self._check_cancellation()
        evaluation = self.candidate_evaluator.evaluate(
            subgraph_id,
            self.state,
            is_first=is_first,
            max_workers=max_workers,
        )
        self.state.cluster_details[subgraph_id] = evaluation.cluster_details
        return evaluation.result

    def _store_result(self, result: OptimizationResult) -> None:
        self.state.opt_results_central[result.subgraph_id] = (
            result.central_cost,
            result.results_central,
        )
        self.state.opt_results_decentral[result.subgraph_id] = (
            result.decentral_cost,
            result.results_decentral,
        )

    def _append_iteration(
        self,
        *,
        step: int,
        result: OptimizationResult,
        previous_central_cost: float,
        distance_to_grid: float | None = None,
    ) -> None:
        self.state.iteration_history.append(
            IterationRecord(
                step=step,
                subgraph_id=int(result.subgraph_id),
                decision=("connected" if result.is_connected else "rejected"),
                central_cost_total=float(result.central_cost),
                previous_central_cost=float(previous_central_cost),
                marginal_central_cost=float(result.central_cost - previous_central_cost),
                decentral_cost=float(result.decentral_cost),
                grid_cost_raw=float(result.grid_cost),
                connection_length_m=float(result.connection_length),
                cumulative_connected_ids=[
                    int(subgraph_id) for subgraph_id in self.state.connected_subgraphs
                ],
                connecting_path_nodes=result.connecting_path_nodes,
                distance_to_grid=(
                    float(distance_to_grid) if distance_to_grid is not None else None
                ),
            )
        )

    def _record_loop_metrics(self, wall_start: float) -> None:
        central_total = sum(self.perf.metrics.get("central_model_build_and_solve", []))
        decentral_sum = sum(self.perf.metrics.get("decentral_model_build_and_solve", []))
        self.perf.add_optimization_metric("central_solve_time_total", central_total)
        self.perf.add_optimization_metric("decentral_solve_time_sum", decentral_sum)
        self.perf.add_optimization_metric(
            "total_optimization_loop",
            time.perf_counter() - wall_start,
        )

    def run_greedy(
        self,
        all_subgraph_ids: Sequence[int],
        max_workers: int | None = None,
    ) -> list[OptimizationResult]:
        """Greedy expansion by shortest distance to the connected grid."""

        demand_lookup = {
            subgraph_id: float(
                self.subgraph_attributes_df.loc[
                    subgraph_id,
                    "Annual Heat Demand [MWh/a]",
                ]
            )
            for subgraph_id in all_subgraph_ids
        }

        initial_subgraph = max(all_subgraph_ids, key=lambda sid: demand_lookup[sid])
        remaining = set(all_subgraph_ids)
        remaining.discard(initial_subgraph)
        results: list[OptimizationResult] = []
        wall_start = time.perf_counter()
        self.state.reset_iteration_history()
        previous_central_cost = 0.0
        total = len(all_subgraph_ids)

        def process_step(i: int, subgraph_id: int, is_first: bool) -> OptimizationResult:
            self._check_cancellation()
            started = time.perf_counter()
            self._candidate_started(subgraph_id, i, total)
            print(
                f"  [{i + 1}/{total}] Subgraph {subgraph_id} ... ",
                end="",
                flush=True,
            )
            try:
                result = self.process_subgraph(
                    subgraph_id,
                    is_first=is_first,
                    max_workers=max_workers,
                )
            except CancellationRequested:
                raise
            except Exception as exc:
                emit_progress(
                    self.observer,
                    "optimization.candidate_failed",
                    {
                        "candidate_id": int(subgraph_id),
                        "index": int(i),
                        "total_candidates": int(total),
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
                raise
            tag = "CONNECTED" if result.is_connected else "skipped"
            duration = time.perf_counter() - started
            print(
                f"{tag} (central={result.central_cost:.0f}, "
                f"decentral={result.decentral_cost:.0f}) "
                f"[{duration:.1f}s]",
                flush=True,
            )
            self._candidate_completed(
                result,
                index=i,
                total=total,
                duration_seconds=duration,
            )
            self._check_cancellation()
            return result

        result = process_step(0, initial_subgraph, is_first=True)
        results.append(result)
        self._store_result(result)
        self._append_iteration(
            step=0,
            result=result,
            previous_central_cost=0.0,
            distance_to_grid=0.0,
        )
        previous_central_cost = result.central_cost

        step = 1
        while remaining:
            nearest_id, nearest_distance = self._find_nearest_candidate(
                list(remaining),
                demand_lookup,
            )
            if nearest_id is None:
                break

            result = process_step(step, nearest_id, is_first=False)
            results.append(result)
            self._append_iteration(
                step=step,
                result=result,
                previous_central_cost=previous_central_cost,
                distance_to_grid=nearest_distance,
            )
            if result.is_connected:
                previous_central_cost = result.central_cost
            self._store_result(result)
            remaining.discard(nearest_id)
            step += 1

        self._record_loop_metrics(wall_start)
        return results

    def run(
        self,
        sorted_subgraph_ids: Sequence[int],
        max_workers: int | None = None,
    ) -> list[OptimizationResult]:
        """Run the selected candidate order."""

        results: list[OptimizationResult] = []
        wall_start = time.perf_counter()
        self.state.reset_iteration_history()
        previous_central_cost = 0.0

        total = len(sorted_subgraph_ids)
        for i, subgraph_id in enumerate(sorted_subgraph_ids):
            self._check_cancellation()
            started = time.perf_counter()
            self._candidate_started(subgraph_id, i, total)
            print(
                f"  [{i + 1}/{total}] Subgraph {subgraph_id} ... ",
                end="",
                flush=True,
            )
            try:
                result = self.process_subgraph(
                    subgraph_id,
                    is_first=(i == 0),
                    max_workers=max_workers,
                )
            except CancellationRequested:
                raise
            except Exception as exc:
                emit_progress(
                    self.observer,
                    "optimization.candidate_failed",
                    {
                        "candidate_id": int(subgraph_id),
                        "index": int(i),
                        "total_candidates": int(total),
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
                print(f"ERROR: {exc}", flush=True)
                raise

            tag = "CONNECTED" if result.is_connected else "skipped"
            duration = time.perf_counter() - started
            print(
                f"{tag} (central={result.central_cost:.0f}, "
                f"decentral={result.decentral_cost:.0f}) "
                f"[{duration:.1f}s]",
                flush=True,
            )
            self._candidate_completed(
                result,
                index=i,
                total=total,
                duration_seconds=duration,
            )
            self._check_cancellation()
            self._append_iteration(
                step=i,
                result=result,
                previous_central_cost=previous_central_cost,
            )
            if result.is_connected:
                previous_central_cost = result.central_cost

            results.append(result)
            self._store_result(result)

        self._record_loop_metrics(wall_start)
        return results


__all__ = [
    "CandidateEvaluator",
    "ClusterSolver",
    "ConnectionEvaluator",
    "HeatGridOptimizer",
    "IterationRecord",
    "ModelRun",
    "ModelRunner",
    "OptimizationContext",
    "OptimizationResult",
    "OptimizationRunState",
]
