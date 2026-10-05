# DH-COMPASS

DH-COMPASS compares district-heating network expansion and supply with decentralized alternatives. It currently works **only in North Rhine-Westphalia (NRW), Germany**, using regional building-demand and heat-potential data.

## Setup and commands

```bash
uv sync --locked
uv run pytest
uv run dh-compass run --config configs/scenarios/bad_oeynhausen.toml
uv run dh-compass charts outputs/bad_oeynhausen/<timestamp>/full_results.json
```

Historical temperatures are loaded automatically for the selected area using
Open-Meteo ERA5-Land, then cached by location and year. The default
weather year is 2022; change `demand.slp_year` to another completed year.
Demand profiles and heat-pump calculations use the same local weather.

For the local browser application, install the optional web dependencies and
build or serve the frontend:

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

The web command serves `frontend/dist` by default.  A wheel deployment can
copy that directory into its release image or set
`DH_COMPASS_WEB_FRONTEND_STATIC_PATH` to a separately built directory.  See
[`docs/frontend/operations.md`](docs/frontend/operations.md) for startup
checks, backups, updates, and troubleshooting.

A full scenario run requires the external geospatial inputs described in
[`data/README.md`](data/README.md). The app prefers Gurobi when its library and
license work, and automatically uses the bundled HiGHS solver otherwise.
`uv sync` installs HiGHS; no solver license is required for the fallback.
The unit tests use small in-memory data and mock solver calls.

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

## License and source transfer

DH-COMPASS is licensed under [MIT](LICENSE), with the approved copyright:
Copyright (c) 2026 Chair of Energy Economics, Universität Duisburg-Essen.

Dependencies retain their terms in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Full provider workbooks and geospatial inputs are excluded from the source archive;
production runs use local
inputs described in [data/README.md](data/README.md). Existing parameters and
configuration remain unchanged. A separate CC BY 4.0 resource bundle is available;
the NRW GDB must be supplied locally. The slim attributed HEF03/HMF03 coefficient
JSON is bundled by default; additional profiles require a local input override.
See [SLP setup and provenance](docs/slp-inputs.md).
See [DATA_LICENSES.md](DATA_LICENSES.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

For transfer to a new repository without history:

```bash
uv run python scripts/export_source.py
uv run python scripts/release_audit.py --archive outputs/release/DH-COMPASS-source.zip
```

Extract the ZIP into the new repository. Do not copy the old `.git` directory.
The exporter also works from a source folder without Git metadata. It excludes
provider inputs, environments, caches, outputs and frontend build products.
See [docs/release-checklist.md](docs/release-checklist.md) for release validation.
