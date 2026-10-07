# DH-COMPASS data

- `reference/` contains the bundled project-authored `sh_to_wh_ratio.csv`,
  slim attributed `slp_parameters.json`, and
  locally supplied reference tables. Provider workbooks are ignored and not redistributed.
- `external/` contains large original geospatial datasets such as the NRW GDB
  and heat-supply potential layers. It is ignored; obtain files from the
  relevant provider and keep their licenses with the local copy.
- `cache/` contains downloaded or derived files
  and is ignored.
- `examples/` is reserved for tiny fixtures used by tests and demonstrations.

The default paths are resolved by `dh_compass.config.PathConfig`, so a run does
not depend on the current working directory. Expected inputs include:

| Dataset | Expected path | Source/access and notes |
| --- | --- | --- |
| NRW building heat demand GDB | `external/Warmebedarf_NRW.gdb` | [Official NRW download](https://www.opengeodata.nrw.de/produkte/umwelt_klima/energie/kwp/); obtain KWP-NRW-Waermebedarf_EPSG25832_Geodatabase.zip locally and retain accompanying metadata/terms. EPSG:25832, layer configured in TOML; large and not tracked. |
| Heat supply potentials | `external/heat_supply_potentials/` | Six Fraunhofer Fordatis CC BY 4.0 layers; extract the separate resource ZIP into the project root. [Attribution and installation](../docs/resource-data-bundle/README.md). |
| Reference demand factors | `reference/sh_to_wh_ratio.csv` | Bundled project-authored calendar factors under MIT: `Datum` and `sh_to_wh_ratio`. All 8,760 original timestamps and ratios are retained exactly. The ratios weight decentralized heat-pump COP; unused workbook columns were removed. |
| SLP parameters | `reference/slp_parameters.json` | Bundled HEF03/HMF03 coefficients and weekday factors, with BDEW source and chair transcription credit. Other profiles can use a local JSON/workbook override. [Provenance and schema](../docs/slp-inputs.md). |
| Electricity market tables | `reference/EPEX SPOT DE-LU (Phelix) Stunden.xlsx` and `reference/EEX Phelix-DE Baseload Cal-*.xlsx` | EPEX/EEX market-data exports; retain the applicable licence and do not redistribute restricted data. |
| Local historical weather | `cache/weather/<request-hash>.json` | Automatically acquired from Open-Meteo (ERA5-Land); scoped by coordinates, year, model and request version. No user account or credentials required for non-commercial use. |

Ordinary CLI and web calculations acquire temperature data for the centre of the
selected WGS84 bounding box. Validated matching caches work offline. No legacy CDS/ADS downloader is retained.

For the official NRW heat-demand ZIP dated 2025-08-07, prepare the extracted GDB
with `uv run python scripts/prepare_nrw_gdb.py data/external/Warmebedarf_NRW.gdb`.
This corrects two OBJECTID metadata flags without changing feature values or
geometries. `Nutzflaeche` is read as the existing `NF` model field. See the
repair implementation in src/dh_compass/preprocessing/filegdb.py and its tests.

Provider originals should remain local unless their terms permit redistribution.
Tests need no original provider workbooks; the bundled SLP defaults are checked
directly. See [DATA_LICENSES.md](../DATA_LICENSES.md).

For authorized production workbooks, preserve the existing schema:

- Calendar CSV: `Datum` ISO timestamps, `sh_to_wh_ratio` in [0, 1]. Existing Excel path overrides remain supported.
- Heat SLP: sheets `Parameter` and `Tagesfaktoren`; category, characteristic
  (`Sigmoid_SigLinDe` + `ausprÃ¤gung`), A/B/C/D, m_H/b_H/m_w/b_w, seven day factors.
- Variable market prices: provider workbook layout with four header rows;
  EPEX `Datum`, `Stunde`, `Preis`, `Umsatz`; EEX dated index and `Preis`.
  Prefer fixed prices unless you have authorized market data.
- Geospatial layers: configured layer and scenario columns; inspect CRS before
  selecting or reprojecting. Record conversion/filter commands with the source.

The project includes the project-authored ratio CSV and attributed SLP JSON.
Other provider data must be obtained separately and handled under its applicable
license.
