"""Sequential and parallel decentralized cluster solving."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from mip import MipBaseException, ProgrammingError

from ..observability.performance import PerformanceTracker
from .context import OptimizationContext
from .model_runner import ModelRun, ModelRunner
from .result_extraction import ModelSolution

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClusterSolveRecord:
    """Value-only result and timings for one representative cluster."""

    cluster_id: int
    obj_val: float
    centroid_demand: float
    total_demand: float
    n_buildings: int
    scaled_cost: float
    build_time: float = 0.0
    solve_time: float = 0.0
    slp_time: float = 0.0
    solution: ModelSolution | None = None

    @property
    def portfolio(self) -> dict[str, object] | None:
        if self.solution is None:
            return None
        return self.solution.to_portfolio_dict()

    def to_worker_dict(self) -> dict[str, object]:
        """Return the serializable cluster detail representation."""

        result = {
            "cluster_id": self.cluster_id,
            "obj_val": self.obj_val,
            "centroid_demand": self.centroid_demand,
            "total_demand": self.total_demand,
            "n_buildings": self.n_buildings,
            "scaled_cost": self.scaled_cost,
            "build_time": self.build_time,
            "solve_time": self.solve_time,
            "slp_time": self.slp_time,
        }
        if self.solution is not None:
            result["solution"] = self.solution
            result["portfolio"] = self.portfolio
        return result


class ClusterSolveError(RuntimeError):
    """A worker failed while solving one parallel cluster."""

    def __init__(self, cluster_id: int, cause: Exception) -> None:
        self.cluster_id = cluster_id
        self.cause = cause
        super().__init__(f"cluster {cluster_id} failed: {cause}")


class ClusterSolver:
    """Generate representative profiles and solve decentralized clusters."""

    def __init__(
        self,
        context: OptimizationContext,
        *,
        model_runner: ModelRunner | None = None,
        performance_tracker: PerformanceTracker | None = None,
    ) -> None:
        self.context = context
        self.model_runner = model_runner or ModelRunner(context)
        self.performance_tracker = performance_tracker

    def solve_one(
        self,
        cluster_id: int,
        cluster_info: Mapping[str, object],
        *,
        gurobi_threads: int | None = None,
    ) -> ClusterSolveRecord:
        """Solve one representative cluster without scaling its model."""

        centroid_demand = float(cluster_info["centroid_demand"])
        total_demand = float(cluster_info["total_demand"])
        n_buildings = int(cluster_info["n_buildings"])

        if centroid_demand <= 0:
            return ClusterSolveRecord(
                cluster_id=cluster_id,
                obj_val=0.0,
                centroid_demand=centroid_demand,
                total_demand=total_demand,
                n_buildings=n_buildings,
                scaled_cost=0.0,
            )

        profile_generator = self.context.runtime_services.building_profile_generator
        if profile_generator is None:
            raise RuntimeError(
                "A building_profile_generator is required for decentralized clusters"
            )

        profile_start = time.perf_counter()
        building_load = profile_generator(centroid_demand)
        slp_time = time.perf_counter() - profile_start

        run: ModelRun = self.model_runner.run(
            building_load,
            decentral=True,
            solver_threads=gurobi_threads,
            use_gathered_results=False,
            record_performance=False,
        )
        scale_factor = total_demand / centroid_demand
        return ClusterSolveRecord(
            cluster_id=cluster_id,
            obj_val=run.objective_value,
            centroid_demand=centroid_demand,
            total_demand=total_demand,
            n_buildings=n_buildings,
            scaled_cost=run.objective_value * scale_factor,
            build_time=run.timing.build_time,
            solve_time=run.timing.solve_time,
            slp_time=slp_time,
            solution=run.solution,
        )

    def solve(
        self,
        clusters: dict[int, dict[str, object]],
        *,
        max_workers: int | None = None,
        gurobi_threads: int | None = None,
    ) -> tuple[float, dict[int, dict[str, object]]]:
        """Solve clusters sequentially or in parallel and scale their costs."""

        if max_workers is not None and max_workers > 1:
            records = self._solve_parallel(
                clusters,
                max_workers,
                gurobi_threads=gurobi_threads,
            )
        else:
            records = self._solve_sequential(clusters)

        self._record_timings(records)
        total_cost = sum(record.scaled_cost for record in records.values())
        cluster_costs = {
            cluster_id: {
                "cost": record.obj_val,
                "centroid_demand": record.centroid_demand,
                "n_buildings": record.n_buildings,
                "building_indices": clusters[cluster_id]["building_indices"],
                "total_demand": record.total_demand,
                "scaled_cost": record.scaled_cost,
                "solution": record.solution,
                "portfolio": record.portfolio,
            }
            for cluster_id, record in records.items()
        }
        return total_cost, cluster_costs

    def _solve_sequential(
        self,
        clusters: dict[int, dict[str, object]],
    ) -> dict[int, ClusterSolveRecord]:
        return {
            cluster_id: self.solve_one(cluster_id, cluster_info)
            for cluster_id, cluster_info in clusters.items()
        }

    def _worker_entry(
        self,
        cluster_id: int,
        cluster_info: Mapping[str, object],
        gurobi_threads: int,
    ) -> ClusterSolveRecord:
        """Normalize only retryable parallel-worker failures.

        Sequential retry is reserved for solver-backend failures and OS-level
        worker/resource faults, which can be caused by concurrent execution or
        the per-worker solver-thread limit.  Validation and programming errors
        propagate unchanged: rerunning them sequentially cannot fix them and
        would obscure their cause.  ``mip.ProgrammingError`` is explicitly
        excluded even though it inherits from ``MipBaseException``.
        """

        try:
            return self.solve_one(
                cluster_id,
                cluster_info,
                gurobi_threads=gurobi_threads,
            )
        except ProgrammingError:
            raise
        except (MipBaseException, OSError) as exc:
            raise ClusterSolveError(cluster_id, exc) from exc

    def _solve_parallel(
        self,
        clusters: dict[int, dict[str, object]],
        max_workers: int,
        *,
        gurobi_threads: int | None = None,
    ) -> dict[int, ClusterSolveRecord]:
        if gurobi_threads is None:
            total_cores = os.cpu_count() or 4
            gurobi_threads = max(1, total_cores // max_workers)
        results: dict[int, ClusterSolveRecord] = {}
        failures: dict[int, ClusterSolveError] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self._worker_entry,
                    cluster_id,
                    cluster_info,
                    gurobi_threads,
                ): cluster_id
                for cluster_id, cluster_info in clusters.items()
            }
            for future in as_completed(futures):
                cluster_id = futures[future]
                try:
                    results[cluster_id] = future.result()
                except ClusterSolveError as exc:
                    failures[cluster_id] = exc

        for cluster_id, failure in failures.items():
            logger.warning(
                "%s; retrying sequentially without a per-worker thread limit",
                failure,
            )
            results[cluster_id] = self.solve_one(
                cluster_id,
                clusters[cluster_id],
            )

        return results

    def _record_timings(self, records: Mapping[int, ClusterSolveRecord]) -> None:
        if self.performance_tracker is None:
            return
        for record in records.values():
            self.performance_tracker.metrics.setdefault(
                "decentral_model_build", []
            ).append(record.build_time)
            self.performance_tracker.metrics.setdefault(
                "decentral_model_solve", []
            ).append(record.solve_time)
            self.performance_tracker.metrics.setdefault("slp_generation", []).append(
                record.slp_time
            )
            self.performance_tracker.metrics.setdefault(
                "decentral_model_build_and_solve", []
            ).append(record.build_time + record.solve_time)

__all__ = [
    "ClusterSolveError",
    "ClusterSolveRecord",
    "ClusterSolver",
]
