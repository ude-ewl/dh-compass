# Biomass allocation: setup and interpretation

The default is **whole-municipality population allocation**. A neighbourhood
inside Brilon receives Brilon's population-weighted share of Arnsberg's complete
regional biomass budget, not a share based on the neighbourhood's area or population.

```text
fuel budget = regional Bio_TWh × 1,000,000
              × municipality population / complete NUTS2 population
              × project budget fraction
```

`Bio_TWh` is annual **fuel energy**, with the source's 50% availability to district
heating already applied. Do not halve it again or apply boiler/CHP efficiency to
the allowance. Boiler and CHP fuel inputs share one cap; useful heat is lower
and is calculated using technology efficiencies.

## Offline inputs

The canonical configuration directly reads the supplied local BKG VG250-EW file:

```toml
[resources]
biomass_allocation_method = "municipality_population"
biomass_population_path = "data/external/vg250-ew_ebenen_1231/DE_VG250.gpkg"
biomass_municipality_ags = []
biomass_budget_fraction = 1.0
```

Use the **31 December 2024** population vintage. Other vintages need a reviewed
update to population completeness and NUTS compatibility checks. The loader
requires 396 unique NRW land-record municipalities, explicit official NUTS2
assignments, and exact reconciliation against all five regional populations.
Water records (`GF != 4`) are excluded. National data is filtered before caching;
study-area filtering never changes the regional denominators.

For a smaller, checksum-pinned input, prepare it explicitly from the original:

```bash
uv run python scripts/prepare_biomass_population.py
```

This creates:

- `data/cache/biomass/municipal_allocation_2024.gpkg`
- `data/cache/biomass/municipal_allocation_2024.manifest.json`

Then override `biomass_population_path` with the prepared GeoPackage path. Both
files are required: a missing or mismatched manifest blocks calculation. The
script leaves the original untouched, verifies geography and population first,
and performs no downloads. CLI-relative preparation paths are project-relative.
Ordinary configured paths are resolved through `PathConfig`, not the working directory.

When regenerating after switching configuration to the prepared file, supply
`--source data/external/vg250-ew_ebenen_1231/DE_VG250.gpkg` explicitly. Generated
GeoPackages/manifests stay under ignored `data/cache/`, not in Git or the code bundle.

## Automatic municipality selection

The executed WGS84 **bounding box** determines municipality candidates. Uploaded
polygon outlines remain presentation/audit information; they do not replace the
executed rectangle. Positive-area overlaps count; boundary-only contact does not.
Intersections are formed in WGS84 and measured in EPSG:25832, avoiding projection
chord slivers at shared edges.

- Automatically select the municipality with the **largest overlap area** and
  use its **entire population**, even when the study crosses municipal borders.
- Exact overlap ties are resolved deterministically by ascending AGS.
- Optional explicit AGS overrides can select one or more intersecting municipalities;
  these take precedence over automatic selection.
- Uncovered areas, unknown AGS, incomplete populations or unsupported geography:
  block calculation rather than invent zero potential or silently use area mode.

Example:

```toml
[resources]
biomass_municipality_ags = ["05958012"] # Brilon, including its districts
```

VG250 is generalized to 1:250,000, not parcel-accurate. A conflicting tiny-border
selection may need a reviewed higher-resolution boundary source; the implementation
does not silently grant a non-intersecting municipality's quota.

## Independent studies and concurrent projects

Each independent Brilon study at fraction 1 can test access to the same
**14,596.707464770829 MWh/year fuel budget**. Runs do not reserve or consume fuel,
and these allowances must not be added across independent studies.

Concurrent projects must manually coordinate fractions, for example 0.6 and 0.4,
or be optimized together. `biomass_budget_fraction` is a scenario assumption in
[0, 1], not an enforced reservation ledger. Fraction zero disables biomass through
the existing zero-limit technology gating. Within a run, cumulative central
solves reuse one unchanged study budget as connected demand grows.

## Reproducing older studies

```toml
[resources]
biomass_allocation_method = "area"
biomass_budget_fraction = 1.0
```

This preserves the previous selected-area weighting without requiring population
data. For the Brilon example it gives **229.0039229561917 MWh/year**. The population
default is an intentional modelling-assumption change, not a solver regression.
Disabling biomass requires neither its potential file nor population data.

Allocation-only checks with the local source files and configured AGS:

| Scenario | Population fuel budget, MWh/a | Legacy area budget, MWh/a |
| --- | ---: | ---: |
| Bad Oeynhausen | 44,856.9348 | 14,841.9020 |
| Brilon | 14,596.7075 | 229.0039 |
| Kamen | 24,296.6513 | 29,591.8750 |
| Mettmann | 8,684.7191 | 50,667.7785 |

These are input allowances, not optimized fuel use or costs. Full production
solver comparisons of capacities, grid connections and costs remain outstanding.

## Provenance and compatibility

New `full_results.json` and `viewer_data.json` contain
`resource_allocations.biomass`; `data_provenance.json` contains the same allocation.
It records method, AGS/names, full municipal/regional populations, shares, regional
potentials, project fraction, source hashes, dates, fuel units and attribution.
The web supply endpoint exposes this metadata; older result files without it
remain readable. Setting changes affect the run identity without discarding the
building/network preview. Readiness fingerprints also include allocation inputs.

The potential is a **2050** source scenario. **2024** population is an allocation
proxy, not a forecast. Eurostat's three amendment workbooks establish unchanged
NRW NUTS classification from 2013 through 2024; every one of the 396 local municipal
representative points also agrees with its explicitly assigned regional polygon.
This does not assert identical generalized polygon vertices across releases.
See [the source verification](biomass-data-semantics.md#5-nuts-2013-to-2024-compatibility).

## Sources and licensing

- Existing potential: [Manz et al., Fordatis 341.2](https://fordatis.fraunhofer.de/handle/fordatis/341.2),
  **CC BY 4.0**. Fuel reconstruction is documented in
  [biomass-data-semantics.md](biomass-data-semantics.md).
- Population and administrative boundaries:
  [BKG VG250-EW](https://gdz.bkg.bund.de/index.php/default/digitale-geodaten/verwaltungsgebiete/verwaltungsgebiete-1-250-000-mit-einwohnerzahlen-stand-31-12-vg250-ew-31-12.html),
  **Datenlizenz Deutschland – Namensnennung – Version 2.0**
  ([dl-de/by-2-0](https://www.govdata.de/dl-de/by-2-0)).
- Retain **© BKG**, the year of acquisition/access, source URL,
  [underlying data-source notes](https://sgx.geodatenzentrum.de/web_public/gdz/datenquellen/datenquellen_vg_nuts.pdf),
  and NRW filtering/normalization modification notes. Preparation records its
  year and attribution; direct reads record the access year.
- [Source checksum record](licenses/biomass-population-manifest.json).
  Neither original nor prepared population data is redistributed with code or
  added to the six-file Fordatis bundle. Keep license/provenance information
  with any separately redistributed preparation.
