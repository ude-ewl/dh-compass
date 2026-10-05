# PROJECT KNOWLEDGE BASE

DH-COMPASS is a Python heat-grid optimization tool for NRW.

## Canonical commands

```bash
uv sync
uv run pytest
uv run dh-compass run --config configs/scenarios/bad_oeynhausen.toml
uv run dh-compass charts outputs/<scenario>/<timestamp>/full_results.json
uv run ruff check .
```

A valid Gurobi/MIP solver installation may be required for full production
runs. Unit tests mock the solver boundary whenever possible.

## Architecture

- `src/dh_compass/cli.py` — command-line entry point.
- `src/dh_compass/pipeline.py` — visible, testable application stages.
- `src/dh_compass/config/` — typed TOML configuration and path resolution.
- `src/dh_compass/preprocessing/` — buildings, OSM, heat density, candidate areas.
- `src/dh_compass/resources/` — location-dependent heat potentials.
- `src/dh_compass/demand/` — heat/electric profiles, COP, runtime factories.
- `src/dh_compass/network/` — routing and network costs.
- `src/dh_compass/optimization/` — context, model, clustering, orchestration.
- `src/dh_compass/economics/` — annuity and cost-curve calculations.
- `src/dh_compass/reporting/` — result schema, JSON, viewer, and charts.
- `src/dh_compass/observability/` — performance metrics.
- `tests/` — unit and integration protection.

## Data and configuration

Scenario TOML files live under `configs/`. Input data belongs under `data/`:
`reference/` for small versioned tables, `external/` for large provider data,
`cache/` for downloads/derived data, and `examples/` for tiny fixtures. Generated
runs belong under `outputs/<scenario>/<timestamp>/` and never under `src/` or
`data/reference/`.

All filesystem paths are `pathlib.Path` values resolved by `PathConfig`; code
must not rely on the current working directory.

## Import direction and coding rules

Configuration flows into preprocessing, demand, and resources; those feed an
explicit optimization context; optimization feeds reporting. Core modules must
not import the CLI or notebooks. Do not add import-time file I/O, downloads,
solver work, expensive calculations, `sys.path` manipulation, or wildcard
imports. Keep package initializers small and re-export only explicit public APIs.

When changing optimization behavior, add or update characterization tests and
keep the solver-dependent portion isolated behind mocks in ordinary unit tests.

## Frontend presentation

The default workflow is NRW area → calculation → final combined results. English/German lives in `frontend/src/i18n`; UI components subscribe through `useLocale()` and translate presentation with `tr()`/`t()`. Preserve placeholders, units, user input, IDs and API numeric values. Switching must retain form/map state and active work. Run frontend lint/typecheck/unit/browser/build/license checks for UI changes.
