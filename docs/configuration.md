# Configuration

Use TOML files under `configs/`:

```bash
uv run dh-compass run --config configs/scenarios/bad_oeynhausen.toml
```

`configs/default.toml` is the single source of truth for scenario, network,
demand, optimization, economic, resource, and technology defaults. Scenario
files inherit the defaults and override case-specific choices such as the
bounding box. The loader validates the merged document and returns an immutable
`AppConfig` composed of:

- `ScenarioConfig` — case, bounding box, screening threshold, and enabled
  resources;
- `PathConfig` — repository-relative input, cache, template, and output paths;
- `NetworkConfig` — FLH, LHD, pipeline, infrastructure, and network cost-curve
  settings;
- `DemandConfig` — SLP, temperature, COP, and timestep settings;
- `OptimizationConfig` — ordering, workers, clustering, and storage sizing;
- `EconomicsConfig` and `TechnologyConfig` — model defaults and cost curves;
- `ResourceConfig` and `OutputConfig` — potential layers and generated output.

Load configuration explicitly when embedding the application:

```python
from dh_compass.config import load_config

config = load_config("configs/scenarios/bad_oeynhausen.toml")
```

Runtime arrays, COP values, load profiles, cost functions, and resource
availability are created by factories in `demand/runtime.py` and
`optimization/context.py`; they are not configuration globals. These factories
produce the grouped `OptimizationContext` consumed by the optimization API.

Invalid required keys, unsupported enum-like values, and out-of-range numeric
values raise a `ConfigurationError` naming the affected section and key.
Relative paths are resolved through `PathConfig` from the project root,
independently of the current working directory. Resource filenames without a
directory are resolved under `paths.heat_supply_data`; scenario files can
override either the base path or an individual resource path.

Generated run artifacts are written below
`outputs/<scenario>/<timestamp>/` unless an explicit output directory is passed
to `run_pipeline`. No configuration or data files are read at package import
time.

## District-heating distribution losses

`network.heat_loss_fraction` defaults to `0.125` (12.5% of heat entering the
network). It must be finite and in `[0, 1)`. For example:

```toml
[network]
heat_loss_fraction = 0.10
```

Central supply and source-side pump sizing use `delivered_heat / (1 - fraction)`
at every timestep. Set `0.0` to reproduce loss-free calculations. Building demand,
heat-density screening, building connections/transfer stations and decentralized
benchmarks are unchanged. Generator efficiency, COP and storage losses remain
separate. This is a constant-fraction planning approximation, not a spatial
pipe-loss or hydraulic model.

Exported `demand_heat`, annual demand and demand peaks remain delivered heat.
Central result frames add `network_input_heat` and `distribution_heat_loss` in
kW. Final summaries and combined-network results add `heat_loss_fraction`,
`annual_network_input_heat_mwh`, `annual_distribution_heat_loss_mwh` and
`network_input_peak_load_kw`. Cumulative supply metrics apply to the accepted
network at that step, not just the newly connected candidate. Annual loss
metrics integrate the profile with `dt`; they are not inferred from technology
production, which may also cover storage losses or dumped heat. Heat-cost
comparisons retain delivered heat as their denominator.

## Browser settings and coverage

The released browser submits only an NRW bbox and uses server defaults. Edit scenario TOML for CLI runs or server defaults for new browser runs to change model assumptions, and validate/restart the deployment as appropriate. Completed results retain their immutable configuration. Language is a browser preference, not a model setting. Beyond NRW, regional inputs and loading/coverage checks must be adapted.
