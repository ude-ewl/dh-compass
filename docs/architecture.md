# Architecture

DH-COMPASS is a `src`-layout Python package. The application entry points are
`dh_compass.cli` and `dh_compass.pipeline.run_pipeline`.

```text
AppConfig → preprocessing / demand / resources → OptimizationContext
          → ModelInputs → solver model → ModelSolution
          → OptimizationResult / reporting → JSON, charts, viewer
```

## Package boundaries

- `config/` loads immutable, typed configuration from TOML. `PathConfig` resolves
  every path from the project root.
- `preprocessing/` loads buildings and street networks, calculates heat density,
  and constructs candidate areas.
- `demand/` creates profiles, market series, technology inputs, and COP arrays
  through explicit factories.
- `resources/` assesses location-dependent heat potentials.
- `network/` owns routing and network cost curves.
- `optimization/` owns the validated runtime context, mathematical model, solver
  extraction, and workflow services. `ModelInputs` is the complete boundary for
  one central or decentralized model build. `ModelRunner` builds and solves one
  model, `ClusterSolver` handles decentralized benchmarks,
  `ConnectionEvaluator` handles routing and network costs, and
  `CandidateEvaluator` makes one connection decision. `HeatGridOptimizer`
  coordinates these services and exposes the run workflow.
- `reporting/` consumes `ModelSolution` and `OptimizationResult` values. It owns
  schema assembly, portfolio presentation, cost breakdowns, JSON serialization,
  charts, and viewer exports. It does not inspect solver variables.
- `observability/` owns performance metrics.

## Public optimization contracts

Construct a context from explicit application inputs, then adapt it for a model
run rather than passing a long list of solver arguments:

```python
from dh_compass.optimization import build_model_inputs, build_optimization_context
from dh_compass.optimization.model import generate_deterministic_model_mip

context = build_optimization_context(config, time_series, resources)
model_inputs = build_model_inputs(context, demand_heat, decentral=False)
model = generate_deterministic_model_mip(model_inputs)
```

The principal value objects are:

- `OptimizationContext` — grouped economic, market, demand, technology,
  resource, network, clustering, and runtime-service inputs;
- `ModelInputs` — validated inputs for exactly one model mode and demand profile;
- `ModelSolution` — solver-independent capacities, energy flows, dimensions, and
  optional time-series values;
- `OptimizationResult` — the central/decentralized candidate decision and its
  connection-cost data.

`ModelRunner` normally hides model construction and solver invocation and
returns a `ModelRun` containing a `ModelSolution`, objective value, and timing.
Reporting receives these value objects and only converts native NumPy/Pandas
values at the serialization boundary.

Modules do not read files, download data, or solve models when imported. Core
optimization modules do not import reporting; data flows one way from
optimization into reporting. Generated files belong under
`outputs/<scenario>/<timestamp>/`.

## Refactoring regression baseline

The stored Brilon characterization fixture is a regression reference; comparisons require matching inputs/configuration, not merely the same scenario name. After a
solver-affecting change, run `configs/scenarios/brilon.toml` and compare its
`full_results.json` with `tests/fixtures/brilon_baseline.json`:

```bash
uv run dh-compass run --config configs/scenarios/brilon.toml
uv run python scripts/verify_scenario_baseline.py outputs/brilon/<timestamp>/full_results.json
```

The comparison uses an absolute tolerance of 0.01 in the result's native units
and checks connection decisions, aggregate central/decentralized costs, the
central-model objective, network and pump costs, demand, selected capacities,
and annual energy.

## Browser presentation

The NRW bbox command uses the same Python pipeline with server defaults. English/German presentation does not modify configuration, solver behavior or artifacts. See [frontend architecture](frontend/technical-architecture.md).
