# DH-COMPASS resource data, version 1

Six resource layers from Fraunhofer Fordatis 341.2 are available under CC BY
4.0. See ATTRIBUTION.md and the complete LICENSE-CC-BY-4.0.txt. The 2023 source
version is pinned for reproducibility;
newer upstream versions are not silently substituted.

Extract the ZIP into your project root. Files are placed in
`data/external/heat_supply_potentials/`, matching default configuration paths.
Keep the included `resource-data-bundle/` notices with any redistributed copy.
Verify SHA256SUMS.txt or the archive's sibling `.sha256` file before use.

The archive contains no NRW building GDB, BDEW SLP table, weather or market data.
Those have separate acquisition requirements in `data/README.md`.

Build the bundle from local source inputs with:

```bash
uv run python scripts/export_resource_data.py
```

The exporter verifies the expected hashes, CRS, and required columns and refuses
changed inputs. It does not download or modify data.
