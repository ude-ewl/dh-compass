# DH-COMPASS

DH-COMPASS compares district-heating network expansion and supply with decentralized alternatives. It currently works **only in North Rhine-Westphalia (NRW), Germany**, using regional building-demand and heat-potential data.

## Installation

Install the Python application and its locked dependencies with
[uv](https://docs.astral.sh/uv/):

```bash
uv sync --locked
uv run dh-compass --help
```

A production run also needs the local NRW building-demand database and heat
supply potential layers listed in [`data/README.md`](data/README.md). In
particular, place the prepared building database at
`data/external/Warmebedarf_NRW.gdb` (https://www.opengeodata.nrw.de/produkte/umwelt_klima/energie/kwp/KWP-NRW-Waermebedarf_EPSG25832_Geodatabase.zip) and extract the resource bundle
`data/external/heat_supply_potentials/` (available in 'Releases'), unless the scenario overrides those
paths. These large provider datasets are not included in the repository.

DH-COMPASS prefers Gurobi when its library and licence are available and
otherwise uses the installed HiGHS solver. No solver licence is required for
HiGHS. Run `uv run pytest` to execute the test suite; tests do not require the
external production data.

## Command-line workflow (no browser)

### 1. Choose or create a scenario

Ready-to-edit scenarios are in [`configs/scenarios/`](configs/scenarios/).
Each scenario inherits [`configs/default.toml`](configs/default.toml), so it
only needs to contain values that differ from the defaults. At minimum, give a
run a recognizable `case` and an NRW bounding box in WGS84 coordinate order
`[west, south, east, north]`:

```toml
[scenario]
case = "my_nrw_area"
bbox = [6.95, 51.40, 7.05, 51.48]

# Optional overrides; all other values come from configs/default.toml.
[demand]
slp_year = 2022

[optimization]
max_workers = 4
```

Copy an existing scenario rather than editing `default.toml` when comparing
areas or assumptions. Model settings, cost curves, resource selection, and
input path overrides are documented in
[`docs/configuration.md`](docs/configuration.md). Paths are resolved from the
project root, not from the shell's current directory.

### 2. Run the pipeline

From the repository, run:

```bash
uv run dh-compass run --config configs/scenarios/my_nrw_area.toml
```

The command loads buildings and streets, creates heat-density candidate areas,
assesses local resources, compares district-heating expansion with decentralized
supply, and writes all reports. The first run for a location needs network
access to retrieve its OpenStreetMap road network and Open-Meteo ERA5-Land
weather. Both are cached under `data/cache/`; a matching cache can be reused
offline. Demand profiles and heat-pump calculations use the same local weather.
Use a completed historical year for `demand.slp_year` (2022 by default) to keep
comparisons reproducible.

By default, results are placed in a new timestamped directory:

```text
outputs/<case>/<YYYYMMDDTHHMMSSZ>/
```

For scripts or batch jobs, select the exact destination explicitly:

```bash
uv run dh-compass run \
  --config configs/scenarios/my_nrw_area.toml \
  --output-dir outputs/my_nrw_area/manual-run
```

Use a new output directory for each comparison so an earlier run is not
partially overwritten. Large areas can take a long time and substantially
increase memory and solver requirements; start with a small bounding box.

### 3. Review the artifacts

A successful output directory contains:

- `full_results.json` — canonical summary, final network, supply portfolios,
  annualized costs, and per-candidate decisions;
- `viewer_data.html` and `viewer_data.json` — a standalone local map/report and
  its data (the HTML file can be opened directly, without starting the web app);
- `chart_capacity.png`, `chart_energy_shares.png`, and cost charts — generated
  when the run has a connected network;
- `final_network.geojson` and `lhd_graph.geojson` — accepted network and
  candidate heat-density network for GIS tools, when geospatial export is
  available;
- `performance_metrics.json` — optimization timing and model-size metrics;
- `data_provenance.json` and `weather_provenance.json` — source and weather
  metadata.

Charts can be regenerated from an existing result, optionally into a separate
directory:

```bash
uv run dh-compass charts \
  outputs/my_nrw_area/<timestamp>/full_results.json \
  --output-dir outputs/my_nrw_area/<timestamp>/charts
```

The interpretation and units of reported values are described in
[`docs/methodology.md`](docs/methodology.md). In particular, the reported cost
figures are annualized and the network topology is heuristic rather than a
global topology optimum.

### 4. Use the pipeline from Python (optional)

Automation can call the same browser-independent pipeline directly:

```python
from dh_compass.config import load_config
from dh_compass.pipeline import run_pipeline

config = load_config("configs/scenarios/my_nrw_area.toml")
artifacts = run_pipeline(config, output_dir="outputs/my_nrw_area/api-run")
print(artifacts.output_dir)
print(artifacts.full_results["summary"])
```

The returned `RunArtifacts` also exposes prepared geospatial data, assessed
resources, optimization results, and viewer data for further analysis.

## Browser application (optional)

Install the optional web dependencies and build the frontend:

```bash
uv sync --extra web
cd frontend && npm ci && npm run build && cd ..
uv run dh-compass web --open-browser
```

During frontend development, run the API and Vite in separate terminals:

```bash
uv run uvicorn dh_compass.web.app:create_app --factory --reload
# in a second terminal: cd frontend && npm run dev
```

The web command serves `frontend/dist` by default. A wheel deployment can copy
that directory into its release image or set
`DH_COMPASS_WEB_FRONTEND_STATIC_PATH` to a separately built directory. See
[`docs/frontend/operations.md`](docs/frontend/operations.md) for startup
checks, backups, updates, and troubleshooting.

## Browser workflow

Select an NRW area on the map (search, draw/resize, or enter exact coordinates), then **Start calculation**. Follow progress, reopen work from **Recent runs** and review final network, demand, costs and supply. **Inputs & downloads** contains recorded inputs and files. Accepted runs continue when the browser closes; larger calculations can take a long time.

The header offers **English / Deutsch**, including on mobile. It remembers the choice and changes presentation without clearing the area or altering calculations. Help explains scope, map colors, units and configuration links. Change model settings through [the configuration guide](docs/configuration.md) and repository TOML files. Another region requires corresponding datasets and loading/coverage changes.

## Repository map

```text
configs/                 TOML defaults and scenarios
data/                    reference, external, cache, and example inputs
frontend/                React/TypeScript browser client
src/dh_compass/
  cli.py                 command-line interface
  pipeline.py            application pipeline
  web/                   FastAPI application boundary and metadata foundation
  config/                typed configuration and paths
  preprocessing/         buildings, networks, heat density, candidate areas
  resources/             local heat-resource assessments
  demand/                profiles, COP, and runtime input factories
  network/               routing and network costs
  optimization/          context, model, clustering, orchestration
  economics/             annuities and cost curves
  reporting/             JSON, charts, and viewer exports
  observability/         performance tracking
scripts/                 maintained developer commands
outputs/                 generated runs (ignored)
tests/                   unit and integration tests
```

See [architecture](docs/architecture.md), [configuration](docs/configuration.md),
[methodology](docs/methodology.md), and [data setup](data/README.md).

## License and data

DH-COMPASS is licensed under [MIT](LICENSE), with the approved copyright:
Copyright (c) 2026 Chair of Energy Economics, Universität Duisburg-Essen.

Dependencies retain their terms in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Production runs use the local inputs described in
[data/README.md](data/README.md). A separate CC BY 4.0 resource bundle is
available. Download the NRW GDB from the
[official NRW source](https://www.opengeodata.nrw.de/produkte/umwelt_klima/energie/kwp/KWP-NRW-Waermebedarf_EPSG25832_Geodatabase.zip).
The attributed HEF03/HMF03 coefficient JSON is bundled by default; additional
profiles require a local input override.
See [SLP setup and provenance](docs/slp-inputs.md).
See [DATA_LICENSES.md](DATA_LICENSES.md) and [CONTRIBUTING.md](CONTRIBUTING.md).
