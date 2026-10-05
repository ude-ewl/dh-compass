"""Benchmark full-year scenario LPs in fresh processes (no network during solves).

Prepare once, then compare algorithms/threads against identical input snapshots::

    uv run python scripts/benchmark_solvers.py prepare --config configs/scenarios/brilon.toml
    uv run python scripts/benchmark_solvers.py solve --method auto --threads 1
    uv run python scripts/benchmark_solvers.py solve --method barrier --threads 1

Use a separate invocation for each thread count: HiGHS owns a process-wide
thread scheduler. Solves are cold unless --reuse is explicitly enabled.
Input pickles are trusted local snapshots, never a format for external uploads.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import cloudpickle
import mip
from mip import HIGHS, LP_Method, Model, OptimizationStatus

METHODS = {
    "auto": LP_Method.AUTO,
    "dual": LP_Method.DUAL,
    "primal": LP_Method.PRIMAL,
    "barrier": LP_Method.BARRIER,
    "barrier-no-crossover": LP_Method.BARRIERNOCROSS,
    "ipx": LP_Method.BARRIER,
    "ipx-no-crossover": LP_Method.BARRIERNOCROSS,
    "ipx-dual": LP_Method.BARRIER,
}


def prepare(args: argparse.Namespace) -> None:
    from dh_compass.config import load_config
    from dh_compass.optimization.clustering import cluster_buildings_to_typgebaeude
    from dh_compass.optimization.context import build_optimization_context
    from dh_compass.optimization.model import generate_deterministic_model_mip
    from dh_compass.optimization.model_inputs import build_model_inputs
    from dh_compass.pipeline import load_inputs, prepare_geospatial_data
    from dh_compass.preprocessing.candidate_areas import order_subgraphs
    from dh_compass.resources.assessment import assess_heat_resources

    config = load_config(args.config)
    args.output.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    loaded = load_inputs(config)
    prepared = prepare_geospatial_data(loaded, config)
    resources = assess_heat_resources(config, loaded["bbox"])
    context = build_optimization_context(config, loaded["time_series"], resources)
    ids = order_subgraphs(
        prepared.street_network,
        prepared.subgraph_dict,
        prepared.subgraph_attributes_df,
        config.optimization.subgraph_order,
    )
    rows = prepared.subgraph_attributes_df.set_index("Subgraph ID")
    row = rows.loc[ids[0]]
    demands = row["Building Annual Demands [MWh/a]"]
    clusters = cluster_buildings_to_typgebaeude(
        demands,
        ["Unknown"] * len(demands),
        config.optimization.n_clusters,
        config.optimization.cluster_random_state,
    )
    cases = [("central-first", row["Load Profile"]["load"], False)]
    total_load = sum(rows.loc[i]["Load Profile"]["load"] for i in ids)
    cases.append(("central-all", total_load, False))
    for i, cluster in sorted(clusters.items()):
        demand = context.runtime_services.building_profile_generator(cluster["centroid_demand"])
        cases.append((f"cluster-{i}", demand, True))
    metadata = {
        "scenario": config.case,
        "config": str(args.config.resolve()),
        "cpu_count": os.cpu_count(),
        "platform": platform.platform(),
        "mip_version": mip.__version__,
        "subgraphs": ids,
        "resources": vars(resources),
        "weather": loaded["time_series"].data.attrs.get("weather"),
        "preparation_seconds": time.perf_counter() - start,
        "dt": config.demand.dt,
        "cases": [],
    }
    for name, demand, decentral in cases:
        start = time.perf_counter()
        inputs = build_model_inputs(context, demand, decentral=decentral)
        with patch(
            "dh_compass.optimization.model.create_solver_model", lambda: Model(solver_name=HIGHS)
        ):
            model = generate_deterministic_model_mip(inputs)
        build_seconds = time.perf_counter() - start
        model.verbose = 0
        # Only load these locally generated inputs; pickle is not an exchange format.
        (args.output / f"{name}.pkl").write_bytes(cloudpickle.dumps(inputs))
        item = {
            "name": name,
            "build_seconds": build_seconds,
            "variables": model.num_cols,
            "constraints": model.num_rows,
            "nonzeros": model.num_nz,
            "integer_variables": model.num_int,
            "hours": len(demand),
            "heat_mwh": float(sum(demand) * config.demand.dt / 1000),
            "decentral": decentral,
        }
        metadata["cases"].append(item)
        print(json.dumps(item), flush=True)
        del model
    (args.output / "models.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def solve_one(path: Path, args: argparse.Namespace, cache: dict | None = None) -> dict:
    from dh_compass.optimization.model import (
        generate_deterministic_model_mip,
        update_model_demand,
    )
    from dh_compass.optimization.result_extraction import extract_model_solution

    start = time.perf_counter()
    inputs = cloudpickle.loads(path.read_bytes())
    reused = cache is not None and inputs.options.decentral_bool in cache
    if reused:
        model, previous = cache.pop(inputs.options.decentral_bool)
        # All snapshots in one prepare invocation share these invariant groups.
        inputs = replace(
            previous, demand=replace(previous.demand, demand_heat=inputs.demand.demand_heat)
        )
        assert update_model_demand(model, inputs)
    else:
        model = generate_deterministic_model_mip(inputs)
    if args.normalize:
        model.solver.normalize(float(max(inputs.demand.demand_heat)))
    model.verbose = int(args.verbose)
    build_seconds = time.perf_counter() - start
    model.threads = args.threads
    method = args.reuse_method if reused else args.method
    model.lp_method = METHODS[method]
    if method.startswith("ipx"):
        native_set_option = model.solver._set_string_option_value

        def set_option(name, value):
            native_set_option(name, "ipx" if name == "solver" and value == "ipm" else value)

        model.solver._set_string_option_value = set_option
        if method == "ipx-dual":
            model.solver._set_int_option_value("ipx_dualize_strategy", 1)
    start = time.perf_counter()
    elapsed = model.solver._lib.Highs_getRunTime(model.solver._model)
    error = None
    try:
        status = model.optimize(max_seconds=args.seconds + elapsed)
    except mip.InterfacingError as exc:
        status = OptimizationStatus.ERROR
        error = str(exc)
    solve_seconds = time.perf_counter() - start
    result = {
        "name": path.stem,
        "build_seconds": build_seconds,
        "reused": reused,
        "method": method,
        "solve_seconds": solve_seconds,
        "status": status.name,
        "objective": model.objective_value,
        "error": error,
        "normalization_scale": getattr(model.solver, "normalization_scale", 1),
    }
    if status == OptimizationStatus.OPTIMAL:
        if cache is not None:
            cache[inputs.options.decentral_bool] = (model, inputs)
        solution = extract_model_solution(model, 1.0, objective_value=model.objective_value)
        result["portfolio"] = solution.to_portfolio_dict()
        # Native optimality/feasibility diagnostics do not depend on variable names.
        result["max_primal_infeasibility"] = model.solver._get_double_info_value(
            "max_primal_infeasibility"
        )
        result["max_dual_infeasibility"] = model.solver._get_double_info_value(
            "max_dual_infeasibility"
        )
        for name in ("simplex_iteration_count", "ipm_iteration_count", "crossover_iteration_count"):
            result[name] = model.solver._get_int_info_value(name)
    print(json.dumps({k: v for k, v in result.items() if k != "portfolio"}), flush=True)
    return result


def solve(args: argparse.Namespace) -> None:
    paths = sorted(args.output.glob(args.case + ".pkl"))
    metadata = json.loads((args.output / "models.json").read_text(encoding="utf-8"))
    heat = {case["name"]: case["heat_mwh"] for case in metadata["cases"]}
    paths.sort(key=lambda path: heat[path.stem])
    if not paths:
        raise SystemExit("No prepared models matched --case. Run prepare first.")
    runs = []
    if args.reuse and args.workers != 1:
        raise SystemExit("--reuse benchmark currently requires --workers 1")
    for repeat in range(args.repeats):
        cache = {} if args.reuse else None
        start = time.perf_counter()

        def make_model():
            model = Model(solver_name=HIGHS)
            if args.bulk_updates:
                from dh_compass.optimization.highs_backend import HeatGridHighsSolver

                model.solver = HeatGridHighsSolver(model, "", model.sense)
            return model

        with patch("dh_compass.optimization.model.create_solver_model", make_model):
            if args.workers == 1:
                results = [solve_one(path, args, cache) for path in paths]
            else:
                with ThreadPoolExecutor(max_workers=args.workers) as executor:
                    results = list(executor.map(lambda path: solve_one(path, args), paths))
        runs.append({"wall_seconds": time.perf_counter() - start, "results": results})
        print(json.dumps({"repeat": repeat, "wall_seconds": runs[-1]["wall_seconds"]}), flush=True)
    report = {
        "method": args.method,
        "threads": args.threads,
        "workers": args.workers,
        "cpu_count": os.cpu_count(),
        "case": args.case,
        "reuse": args.reuse,
        "reuse_method": args.reuse_method,
        "bulk_updates": args.bulk_updates,
        "normalize": args.normalize,
        "runs": runs,
    }
    name = f"{args.case}-{args.method}-t{args.threads}-w{args.workers}{'-reuse' if args.reuse else ''}{'-bulk' if args.bulk_updates else ''}.json"
    name = name.replace("*", "all")
    if args.normalize:
        name = name.replace(".json", "-normalized.json")
    if args.reuse and args.reuse_method != "dual":
        name = name.replace(".json", f"-warm-{args.reuse_method}.json")
    (args.output / name).write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "solve"])
    parser.add_argument("--config", type=Path, default=Path("configs/scenarios/brilon.toml"))
    parser.add_argument("--output", type=Path, default=Path("outputs/benchmarks/brilon"))
    parser.add_argument("--method", choices=METHODS, default="auto")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--seconds", type=float, default=180)
    parser.add_argument("--case", default="central-first")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--reuse-method", choices=METHODS, default="dual")
    parser.add_argument("--bulk-updates", action="store_true")
    parser.add_argument("--normalize", action="store_true")
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.normalize and not args.bulk_updates:
        parser.error("--normalize requires --bulk-updates")
    (prepare if args.command == "prepare" else solve)(args)


if __name__ == "__main__":
    main()
