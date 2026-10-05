"""Build and solve one optimization model.

The orchestration layer evaluates many models, but the mechanics of building,
configuring, solving, and extracting one model are the same for central and
decentralized runs.  :class:`ModelRunner` keeps that boundary in one place and
returns value-only results together with timings.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from math import log
from threading import Lock

import pandas as pd
from mip import HIGHS, LP_Method, Model, OptimizationStatus

from ..observability.performance import PerformanceTracker
from .context import OptimizationContext
from .model import ModelStructure, generate_deterministic_model_mip, update_model_demand
from .model_inputs import ModelInputs, build_model_inputs
from .result_extraction import (
    ModelSolution,
    extract_model_solution,
    gather_results_mip,
    model_solution_from_results,
)


@dataclass(frozen=True)
class ModelRunTiming:
    """Time spent building and solving one model, in seconds."""

    build_time: float
    solve_time: float

    @property
    def total_time(self) -> float:
        return self.build_time + self.solve_time


@dataclass(frozen=True)
class ModelRun:
    """Solver-independent output of one model run.

    Orchestration stores this solver-independent value and never needs to
    retain or inspect the solver model after extraction.
    """

    objective_value: float
    solution: ModelSolution
    timing: ModelRunTiming


ModelBuilder = Callable[[ModelInputs], Model]
ResultsGatherer = Callable[
    ...,
    tuple[pd.DataFrame, Mapping[str, Sequence[float]]],
]


def _solution_from_gathered(
    gathered_results: tuple[pd.DataFrame, Mapping[str, Sequence[float]]],
    dt: float,
    objective_value: float,
) -> ModelSolution:
    """Convert gathered solver values into a domain solution."""

    result_df, results_dim = gathered_results
    return model_solution_from_results(
        result_df,
        results_dim,
        dt,
        objective_value=objective_value,
    )


def _peak_distance(model: Model, peak: float) -> float:
    previous_peak = float(model._heatgrid_structure.inputs.demand.demand_heat.max())
    return abs(log(max(previous_peak, 1e-9) / peak))


class ModelRunner:
    """Build, configure, solve, and extract one model.

    The runner deliberately knows nothing about candidate selection or
    clustering.  ``model_builder`` and ``results_gatherer`` are injectable so
    unit tests can replace the solver boundary without
    constructing a production model.
    """

    def __init__(
        self,
        context: OptimizationContext,
        *,
        model_builder: ModelBuilder | None = None,
        results_gatherer: ResultsGatherer | None = None,
        performance_tracker: PerformanceTracker | None = None,
        reuse_models: bool = True,
        max_cached_models: int = 4,
        highs_central_lp_method: str = "barrier",
        highs_decentral_lp_method: str = "barrier",
    ) -> None:
        self.context = context
        self.model_builder = model_builder or generate_deterministic_model_mip
        self.results_gatherer = results_gatherer or gather_results_mip
        self.performance_tracker = performance_tracker
        self.reuse_models = reuse_models
        self.max_cached_models = max_cached_models
        if max_cached_models < 1:
            raise ValueError("max_cached_models must be positive")
        self._models: dict[bool, list[Model]] = {False: [], True: []}
        self._models_lock = Lock()
        methods = {
            "auto": LP_Method.AUTO,
            "dual": LP_Method.DUAL,
            "primal": LP_Method.PRIMAL,
            "barrier": LP_Method.BARRIER,
            "ipx_dual": LP_Method.BARRIER,
        }
        self._highs_methods = {
            False: methods[highs_central_lp_method],
            True: methods[highs_decentral_lp_method],
        }
        self._highs_algorithms = {
            False: highs_central_lp_method, True: highs_decentral_lp_method,
        }

    def run(
        self,
        demand_heat: pd.Series,
        *,
        decentral: bool = False,
        solver_threads: int | None = None,
        use_gathered_results: bool = True,
        performance_name: str | None = None,
        record_performance: bool = True,
    ) -> ModelRun:
        """Run one central or decentralized model.

        ``use_gathered_results`` is enabled for central models because the
        reporting boundary needs their time-series dataframe.  Cluster
        benchmarks only need the compact :class:`ModelSolution` and therefore
        extract directly from solver variables.
        """

        metric_name = performance_name or (
            "decentral_model_build_and_solve" if decentral else "central_model_build_and_solve"
        )

        def execute() -> ModelRun:
            build_start = time.perf_counter()
            model_inputs = build_model_inputs(
                self.context,
                demand_heat,
                decentral=decentral,
            )
            model = None
            if self.reuse_models:
                with self._models_lock:
                    if self._models[decentral]:
                        peak = max(float(demand_heat.max()), 1e-9)
                        cached = self._models[decentral]
                        # Nearby building sizes tend to retain a useful basis.
                        index = min(
                            range(len(cached)),
                            key=lambda i: _peak_distance(cached[i], peak),
                        )
                        model = cached.pop(index)
            reused = model is not None and update_model_demand(model, model_inputs)
            if not reused:
                model = self.model_builder(model_inputs)
            if decentral and model.solver_name == HIGHS and hasattr(model.solver, "normalize"):
                model.solver.normalize(float(demand_heat.max()))
            build_time = time.perf_counter() - build_start

            if model.solver_name == HIGHS:
                # HiGHS shares one global scheduler: every concurrent model
                # must use the same thread count. Cluster workers supply the
                # outer parallelism; serial dual simplex needs only one thread.
                model.threads = 1
                # Central resource limits and aggregate demand changes can make
                # an old basis expensive to repair. Keep the configured method
                # there; nearby representative buildings benefit from dual reuse.
                model.lp_method = (
                    LP_Method.DUAL if reused and decentral else self._highs_methods[decentral]
                )
                model.solver.ipm_algorithm = self._highs_algorithms[decentral]
            elif solver_threads is not None:
                model.threads = solver_threads

            solve_start = time.perf_counter()
            status = model.optimize()
            solve_time = time.perf_counter() - solve_start

            if isinstance(status, OptimizationStatus) and status != OptimizationStatus.OPTIMAL:
                raise RuntimeError(f"Optimization did not reach an optimal solution: {status.name}")

            objective_value = float(model.objective_value)
            if use_gathered_results:
                gathered_results = self.results_gatherer(
                    model,
                    model_inputs.demand.pv_infeed,
                    model_inputs.demand.demand_electric,
                    demand_heat,
                    model_inputs.market.fuel_price,
                    model_inputs.market.elec_price,
                    model_inputs.market.price_sell_pv,
                    model_inputs.market.price_sell_chp,
                    model_inputs.market.dt,
                )
                solution = _solution_from_gathered(
                    gathered_results,
                    model_inputs.market.dt,
                    objective_value,
                )
            else:
                solution = extract_model_solution(
                    model,
                    model_inputs.market.dt,
                    objective_value=objective_value,
                )

            run = ModelRun(
                objective_value=objective_value,
                solution=solution,
                timing=ModelRunTiming(build_time, solve_time),
            )
            if self.reuse_models and isinstance(
                getattr(model, "_heatgrid_structure", None), ModelStructure
            ):
                with self._models_lock:
                    limit = self.max_cached_models if decentral else 1
                    if len(self._models[decentral]) < limit:
                        self._models[decentral].append(model)
            return run

        if self.performance_tracker is not None and record_performance:
            with self.performance_tracker.measure(metric_name):
                run = execute()
            self.performance_tracker.metrics.setdefault(
                "decentral_model_build" if decentral else "central_model_build",
                [],
            ).append(run.timing.build_time)
            self.performance_tracker.metrics.setdefault(
                "decentral_model_solve" if decentral else "central_model_solve",
                [],
            ).append(run.timing.solve_time)
            return run

        return execute()


__all__ = ["ModelRun", "ModelRunTiming", "ModelRunner"]
