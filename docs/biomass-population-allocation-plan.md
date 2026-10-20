# Municipality-population allocation of biomass potential

## Implementation status

Implemented: canonical population/legacy allocation, complete offline VG250-EW
loading/preparation, typed configuration, automatic largest-overlap selection,
readiness checks, bilingual explanations and allocation provenance. The default
reads the supplied original file directly; compact preparation is optional.
[User/setup documentation](biomass-allocation.md) describes the shipped contract.

NRW NUTS2013→2024 classification compatibility is verified using Eurostat's
three amendment workbooks and all 396 local municipal representative points;
see [the verification record](biomass-data-semantics.md#5-nuts-2013-to-2024-compatibility).
Full solver-based scenario cost/capacity comparisons remain a production follow-up.
The sections below preserve the original design and acceptance rationale.
**Selection-policy update:** automatic selection now chooses the municipality
with the largest study-area overlap (ascending AGS breaks exact ties). This
supersedes the original multi-municipality confirmation requirement below.
Optional explicit AGS overrides remain supported; whole municipal population
still determines the fuel budget.

## Recommendation

Adopt municipality-population allocation as the new default for NRW, retaining the existing selected-area allocation as an explicit legacy/sensitivity option.

Treat the result as a **municipal share of a regional biomass supply budget**, not biomass physically produced inside the selected neighbourhood. For an area inside Brilon, use the population of the entire municipality of Brilon, including its districts, exactly as proposed.

This is a reasonable screening assumption for a transportable fuel. It is not evidence of a secured supply contract, nor necessarily a better map of biomass production: forestry and agricultural residues are associated with land use, not population. Population is a transparent allocation rule for competing users of a regional resource.

**Two changes are involved:**

1. Allocation weight: population instead of land area.
2. Allocation scope: the whole municipality instead of the selected study area.

The second change explains much of the increase for small study areas. Population measured only inside the study area would often still produce a small budget and would not implement this proposal.

## 1. Proposed calculation and interpretation

For selected municipalities M and their parent NUTS2 regions r:

```text
municipal_budget_mwh(m)
    = regional_potential_twh(r) × 1,000,000
      × municipality_population(m) / region_population(r)

study_budget_mwh
    = sum(municipal_budget_mwh(m) for unique m in M)
      × biomass_budget_fraction
```

Default `biomass_budget_fraction = 1.0` implements the proposal without further reduction. An optional fraction in [0, 1] represents the share reserved for this project after local commitments or competition; it must not silently repeat reductions already included in the source dataset.

Rules:

- Do not multiply the budget by the selected-area fraction afterward.
- Use populations from the same reporting date and statistical basis.
- Compute each NUTS2 denominator from **all** its municipalities, not only municipalities intersecting the study area.
- Deduplicate municipalities by the eight-character AGS, preserving leading zeros.
- Resolve NUTS membership through administrative codes, not overlap fractions between differently generalized polygons.
- Keep full precision during calculation; round only for presentation.
- Never invent a minimum biomass potential just to make a technology viable.

### Verified Brilon example

Research checked on 12 October 2026. BKG's currently served VG250-EW population vintage is 31 December 2024.

| Input | Verified value |
| --- | ---: |
| Brilon AGS | `05958012` |
| Brilon NUTS3 / parent NUTS2 | `DEA57` / `DEA5` |
| Brilon population | 25,424 |
| NUTS2 Arnsberg population | 3,571,898 |
| Existing `Bio_TWh` for `DEA5` | 2.0507375 TWh/year |
| Population share | 0.711778% |
| Proposed budget, fraction = 1 | 14,596.7075 MWh/year |
| Current allocation for `configs/scenarios/brilon.toml` | 229.0039 MWh/year |

This is approximately **63.7 times** the current allocation. The old value was calculated with the repository's current `assess_biomass` implementation and configured Brilon bounding box. The new value is **fuel energy available to DH**, not delivered heat. Its fuel-energy semantics are now verified by reconstructing all non-null source values; see [the research record](biomass-data-semantics.md).

### Important limitations

- Every separate study of a neighbourhood in Brilon would receive the same municipal budget by default. Those runs are independent screening scenarios, not reservations or allocations that may be added together. Running one study must not reduce the budget seen by another. Projects operating simultaneously must coordinate shares of the one municipal budget or be optimized jointly; see [the worked explanation](biomass-data-semantics.md#4-what-repeated-studies-in-one-municipality-mean).
- Population allocation conserves a regional budget across unique municipalities, but full municipal access does not conserve it across overlapping independent projects.
- Changing municipality at a boundary can produce a step change. This is inherent to the proposal and must be visible to users.
- The source potential describes 2050; 2024 population is a contemporary allocation proxy, not a 2050 population forecast. Record this explicitly.
- Population does not model transport cost, fuel type compatibility, sustainability eligibility, existing contracts or actual market availability. Retain fuel prices and technology efficiencies; do not equate an allocation with guaranteed procurement.
- Municipality heat-demand share would be a useful later alternative and is closer to the source paper's demand-based matching. It requires complete, consistent regional demand totals and should not delay the population method.

## 2. Data research and recommended sources

### Primary: BKG VG250-EW, pinned 31 December 2024 release

One official product supplies municipal polygons, population and administrative/NUTS identifiers. It avoids joining unrelated population grids, name matching or scraping municipal websites.

The required input is now present locally at **`data/external/vg250-ew_ebenen_1231/DE_VG250.gpkg`**. Its municipal layer identifies the reference date as 2024-12-31, and its schema, NRW populations and regional reconciliation have been checked. Use this local file for preparation; no further VG250 download is required. Its checksum and verification are recorded in [the research record](biomass-data-semantics.md#3-local-vg250-ew-file).

- [Product and current population vintage](https://gdz.bkg.bund.de/index.php/default/digitale-geodaten/verwaltungsgebiete/verwaltungsgebiete-1-250-000-mit-einwohnerzahlen-stand-31-12-vg250-ew-31-12.html).
- [Pinned 2024 download directory](https://daten.gdz.bkg.bund.de/produkte/vg/vg250-ew_ebenen_1231/2024/).
- [GeoPackage ZIP, UTM32](https://daten.gdz.bkg.bund.de/produkte/vg/vg250-ew_ebenen_1231/2024/vg250-ew_12-31.utm32s.gpkg.ebenen.zip).
- [Documentation](https://sgx.geodatenzentrum.de/web_public/gdz/dokumentation/deu/vg250.pdf), especially municipal/NUTS assignment, EWZ and GF. The current documentation includes newer structural changes; inspect the actual pinned archive rather than assuming every new field exists.
- [WFS](https://sgx.geodatenzentrum.de/wfs_vg250-ew?service=WFS&request=GetCapabilities) is suitable for research/verification, but is mutable and should not be queried during ordinary optimization.

Read the following from the pinned archive:

| Layer/table | Required content |
| --- | --- |
| `vg250_gem` | `AGS`, `ARS`, `GEN`, `NUTS`, `EWZ`, `GF`, geometry |
| `vgtb_vz_gem` | Explicit municipality-to-NUTS2 assignment, joined through municipal ARS |
| `vg250_rbz` | NRW regional populations for independent denominator reconciliation |

Normalize archive/WFS field casing. Prefer the assignment table's explicit NUTS2 code; checked fallback for NRW is the first four characters of municipal `NUTS` (which is a NUTS3 code).

Filter population-bearing land records using `GF = 4`. BKG documents one such record per administrative unit; additional water records must not double-count population. Multipart geometries already represent a municipality, so exploding polygons must not multiply EWZ. `WSK` is the effective date of an administrative change, **not** the population reference date.

I queried all NRW municipal `GF = 4` records: **396 rows and 396 unique AGS**. Their full regional population sums are:

| NUTS2 | Municipalities | Population, 31 December 2024 |
| --- | ---: | ---: |
| `DEA1` | 66 | 5,244,379 |
| `DEA2` | 99 | 4,486,282 |
| `DEA3` | 78 | 2,659,034 |
| `DEA4` | 70 | 2,072,861 |
| `DEA5` | 83 | 3,571,898 |

All five municipal population sums have now been checked against the local file's same-vintage regional EWZ and match exactly. The preparation step must retain this reconciliation as a validation check.

**License:** dl-de/by-2-0, not MIT. Retain [BKG's attribution and modification requirements](https://sgx.geodatenzentrum.de/web_public/gdz/lizenz/deu/nutzungsbedingungen_vg250.pdf), including data-source links and year of data acquisition. Record NRW filtering/normalization as modifications.

### Boundary precision and alternatives

VG250 geometry is generalized to 1:250,000. It is adequate for unambiguous interior selections, but not a parcel-accurate municipality lookup for tiny areas near a boundary.

For ambiguous locations, support explicit AGS selection. If boundary testing demonstrates insufficient accuracy, use [Geobasis NRW digital administrative boundaries](https://www.wfs.nrw.de/geobasis/wfs_nw_dvg?SERVICE=WFS&REQUEST=GetCapabilities) as the geometry source and join the BKG population/NUTS table by AGS. Pin and validate the boundary vintage and its license separately; do not silently combine mismatched administrative releases.

Other sources:

- [IT.NRW official municipal population publication, 31 December 2024](https://www.statistischebibliothek.de/mir/servlets/MCRFileNodeServlet/NWHeft_derivate_00021716/a123202422.pdf): independent statistical check, not the preferred runtime format.
- [Destatis Gemeindeverzeichnis](https://www.destatis.de/DE/Themen/Laender-Regionen/Regionales/Gemeindeverzeichnis/_inhalt.html): population fallback, joined by AGS and matching reporting date.
- `scripts/rank_ieh_municipalities.py` already demonstrates an OSM-boundary/Destatis join. Its workbook sheet and quarterly URL are hard-coded, and its caches are not present locally. Reuse the AGS concept, not this ad-hoc ingestion as the production contract.

### Existing biomass source: resolved energy semantics and remaining geography check

The repository uses [Fordatis 341.2](https://fordatis.fraunhofer.de/handle/fordatis/341.2), not the Hotmaps biomass dataset. Keep the existing checksum-pinned potential file and CC BY 4.0 attribution.

The [latest metadata workbook](https://fordatis.fraunhofer.de/bitstream/fordatis/341.5/11/Results_DH_Matching_Cluster.xlsx), inspected during this research, describes the layer as:

> Biomass for NUTS2 (2013) areas with available potential for DH in 2050 in TWh ("Bio_TWh").

The [associated paper](https://repositum.tuwien.at/bitstream/20.500.12708/195104/1/Manz-2024-Renewable%20Energy-vor.pdf), sections 2.3 and 2.3.1, describes ENSPRESO's medium 2050 scenario, selected biomass commodities, a 50% availability assumption for DH, and matching regional biomass to DH areas relative to DH demand. It also describes heat delivered to DH and conversion-efficiency assumptions.

**Energy semantics resolved:** all 226 non-null values in the local potential layer reproduce as selected ENSPRESO `ENS_Med` 2050 fuel energy in PJ, divided by 3.6 and multiplied by 0.5. This proves that `Bio_TWh` is fuel energy with the DH availability share already applied, without an additional technology heat-conversion factor. See [the numerical reconstruction and sources](biomass-data-semantics.md). Retain the existing shared **boiler plus CHP fuel-input** constraint; apply neither another 50% reduction nor a heat-efficiency adjustment to the input budget.

Compatibility has now been verified against Eurostat's 2013→2016→2021→2024 amendment workbooks: all 59 NRW NUTS1/2/3 records are unchanged. All 396 local municipal representative points also agree with the biomass source's assigned regional polygons. Runtime rejects inconsistent regional assignments. This checks classification correspondence, not identical generalized boundary vertices; see the [record and workbook hashes](biomass-data-semantics.md#5-nuts-2013-to-2024-compatibility).

## 3. Municipality selection policy

Recommended conservative first implementation:

1. Use the **executed study-area bounding box**, not the scenario name or geocoder label. The current pipeline executes a rectangle; uploaded GeoJSON geometry is currently presentation/audit information in `web/services/study_area.py`.
2. Find candidate municipalities using a spatial index and positive-area intersection in EPSG:25832. Boundary-only contact does not count.
3. If exactly one municipality matches, use its full population automatically.
4. If multiple municipalities match, require an explicit AGS selection from the candidate list. Show names and overlap information. Do not silently choose the centroid municipality, grant every neighbour's entire budget or introduce an arbitrary percentage-overlap threshold.
5. Once the user confirms one or more municipalities, sum each full municipal population share exactly once, with separate denominators for separate NUTS2 regions.
6. Provide the explicit AGS override in CLI/TOML as well as the UI. It must normally be a subset of intersecting candidates. Any tolerance for generalized-boundary discrepancies must be explicit, bounded and audited; otherwise require a higher-resolution boundary source.
7. Missing coverage, an unresolved boundary ambiguity or incomplete population data is an actionable validation error, not zero potential or silent fallback to area allocation.

This preserves the simple Brilon workflow while preventing a slightly expanded bounding box from accidentally claiming a neighbouring city's entire quota. Implement the same resolver in backend readiness and resource assessment so they cannot disagree.

## 4. Implementation phases

### Phase A — characterize current behavior and encode verified semantics

Files: `tests/unit/test_resource_assessment.py`, `src/dh_compass/resources/biomass.py`, `src/dh_compass/resources/assessment.py`.

- Add tests for current area allocation and TWh-to-MWh conversion before refactoring.
- Establish fixtures for the verified Brilon population calculation; keep downloaded real data out of ordinary tests.
- Encode the verified fuel-energy interpretation and already-applied DH availability share in tests and documentation. Complete the remaining NUTS-vintage compatibility check before the new default release.
- There are two implementations of area allocation: the helper in `biomass.py` and inline logic in `assessment.py`. The production pipeline uses the inline implementation. Consolidate them so changes cannot affect only an unused helper.

### Phase B — reproducible, offline-ready data preparation

New script: `scripts/prepare_biomass_population.py`.

- Require an explicit preparation action; no import-time or optimization-time downloads.
- Read the existing `data/external/vg250-ew_ebenen_1231/DE_VG250.gpkg` offline and derive a compact NRW allocation GeoPackage under `data/cache/biomass/`. Do not move or modify the original. Download support is optional for other installations.
- Produce a municipal layer with `ags`, `ars`, `name`, `nuts2`, `population`, geometry and provenance, plus a regional-population table containing the complete denominators.
- Write a companion manifest: source URL, acquisition date, population date, boundary/NUTS vintages, original and derived SHA256, row counts, schema/preparation version, CRS, attribution and modification notes.
- Validate unique identifiers, finite nonnegative municipal populations, positive regional denominators, geometry/CRS, complete NRW coverage, mapping completeness, regional population reconciliation and join coverage against the biomass file.
- Never compute regional denominators after bbox filtering. Do not accept an incomplete municipality file as a smaller region.
- Publish preparation instructions and attribution through `data/README.md`, `DATA_LICENSES.md` and `docs/licenses/`; distribute the new data separately from code unless explicitly approved.

### Phase C — typed configuration and a single allocation implementation

Files: `configs/default.toml`, `src/dh_compass/config/models.py`, `src/dh_compass/config/loader.py`, `src/dh_compass/resources/biomass.py`, `src/dh_compass/resources/assessment.py`.

Proposed resource fields:

```toml
[resources]
biomass_allocation_method = "municipality_population" # alternative: "area"
biomass_population_path = "data/cache/biomass/municipal_allocation_2024.gpkg"
biomass_municipality_ags = [] # empty: automatic only when unambiguous
biomass_budget_fraction = 1.0
```

- Resolve all file paths through existing `PathConfig`-based configuration logic, independent of working directory.
- Validate the method enum, AGS format/duplicates and finite fraction in [0, 1]. Apply the optional fraction consistently to either method.
- Implement pure, testable municipality resolution and population allocation functions with explicit frame/table inputs; separate file loading from computation.
- Return an allocation result containing the numeric budget and provenance/breakdown. Preserve `ResourceAvailability.biomass_energy_limit_mwh` as the solver-facing scalar and carry metadata separately or via an optional typed field with backwards-compatible defaults.
- Make `assessment.py` call the canonical helper for both methods. Preserve other resource behavior.
- Biomass disabled: do not load or require population data. Explicit `area` mode: do not require population data.
- Population mode with missing/invalid enabled-biomass inputs: fail explicitly in CLI and web. Do not silently revert to the old method.

### Phase D — readiness, UI and reporting

Files: `src/dh_compass/web/services/data_readiness.py`, `configuration.py`, `result_adapter.py`, reporting modules, and relevant frontend data/settings/results components.

- Add the population dataset as required only for enabled biomass in population mode.
- Validate selected municipalities, complete regional denominators and source compatibility, not merely dataset extent or file existence. Reuse prepared manifest validation rather than an expensive full national scan per request.
- Offer explicit municipal choices when resolution is ambiguous; support AGS overrides in expert settings.
- Show an allocation explanation, e.g. “Brilon: 25,424 / Arnsberg: 3,571,898; municipal budget for this study.” Translate presentation through `frontend/src/i18n` and `useLocale()` without changing codes, values or units.
- Persist method, resolved municipality IDs/names, population date, NUTS vintage, input hashes, regional values, population shares, fraction and per-municipality allocated MWh in run outputs. Preserve old result-reading compatibility when this metadata is absent.
- Clarify resource-budget units in both final combined results and viewer exports after the semantics check. Display allocated budget separately from actual fuel use and useful heat.
- Include method, fraction, selected AGS and population-data fingerprints in invalidation/run identity. Existing runs remain immutable; changed allocation settings or data require a fresh calculation.

### Phase E — optimizer integration and rollout

Files: `src/dh_compass/optimization/context.py`, `technologies/local_resources.py`, `candidate_evaluator.py`, associated tests and scenario baselines.

- Keep the existing **shared fuel-input** boiler/CHP biomass resource constraint. The source reconstruction confirms this interpretation; no heat/fuel semantic migration is required.
- The current candidate evaluator optimizes cumulative connected demand. Pass the study budget unchanged to these cumulative solves; do not allocate the full municipality budget per candidate and sum historical solutions, and do not subtract previous consumption while reoptimizing the same cumulative system.
- Add mocked characterization tests proving budget forwarding and cumulative behavior. Any solver-dependent checks remain isolated.
- Compare `area` and `municipality_population` for Brilon and the other configured scenarios: allocation, biomass fuel use, technology capacity, connected demand and costs. New results need not be monotonically different because capacity/storage/grid decisions can change.
- Release the new default as an intentional model-assumption change. Provide explicit `area` overrides for reproducing old studies and update configuration fixtures deliberately. Do not treat changed Brilon optimization results as a regression to be hidden by blindly replacing the old baseline.

## 5. Required tests and acceptance criteria

### Unit and configuration tests

- Synthetic example: regional budget 1 TWh, municipal populations 1,000 and 9,000 -> first municipality receives 100,000 MWh, regardless of how small an interior study area is.
- Two different interior selections in the same municipality produce the same allocation.
- Selecting every unique municipality in a complete region recovers its regional budget at fraction 1.
- Multiple selected municipalities in the same and different regions use the right complete denominators.
- Multipart geometry and extra BKG water records never duplicate population.
- Boundary-only contact excluded; multiple candidates require confirmation; unknown/unrelated AGS rejected.
- Missing NUTS mapping, incomplete denominator, duplicate AGS, nonfinite/negative population, invalid geometry/CRS, invalid potential or incompatible source vintage fails with a useful error. Genuine zero-population municipalities contribute zero.
- A zero fraction disables the biomass allowance; no unconstrained technology may survive the zero-limit gating.
- Biomass-off and legacy-area scenarios do not require population data.
- Config path resolution works from an unrelated working directory.
- Pure functions do not mutate input frames; legacy area behavior remains characterized.

### Integration, reporting and UI tests

- `tests/integration/test_pipeline.py`: new allocation scalar and metadata reach outputs; mock the solver and data-loading boundaries.
- Optimization characterization: boiler plus CHP share one budget; cumulative solves do not duplicate it.
- Web readiness: missing population data blocks enabled population allocation but not biomass-off/area mode; ambiguity is actionable.
- English/German selection/explanation rendering retains map/form state; method or AGS changes invalidate work appropriately.
- Older result JSON remains readable; new outputs are reproducible from recorded hashes and parameters.

### Checks

```bash
uv run pytest
uv run ruff check .
```

For UI changes, run the repository's frontend lint, typecheck, unit, browser, build and license checks. Production scenario comparison requires a usable solver installation; it is not a prerequisite for ordinary mocked unit tests.

**Done means:** a small study wholly inside Brilon automatically receives Brilon's full population-weighted municipal budget; users can see its assumptions and provenance; ambiguous borders cannot silently inflate it; incomplete data cannot fabricate it; and separate studies are clearly not additive claims on the same municipal resource.
