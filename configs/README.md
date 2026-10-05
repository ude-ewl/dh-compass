# Configurations

`default.toml` is the canonical default configuration for scenario, network,
demand, optimization, economic, resource, and technology values, including all
cost curves. Repository-relative base paths are intentionally derived by
`PathConfig`; scenario files can override them in a `[paths]` section. Scenario
files under `scenarios/` inherit the defaults and should override only values
that differ.

Run a scenario with:

```bash
uv run dh-compass run --config configs/scenarios/bad_oeynhausen.toml
```

Paths are resolved relative to the repository root unless explicitly set in a
configuration file. The loader validates required tables, enum-like choices,
and numeric ranges before creating the typed immutable configuration. Invalid
configuration reports the offending section and key. Keep credentials and local
dataset locations out of version control.

The normal browser command uses an NRW bbox and server defaults. Advanced settings belong in the TOML/configuration workflow, not the language selector. See [the configuration guide](../docs/configuration.md).
