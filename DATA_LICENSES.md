# Data rights and distribution boundary

Reviewed 5 October 2026. The project's MIT license covers project code,
documentation and the project-authored ratio CSV; it does not relicense provider
data. The maintainer confirmed the MIT release and ratio ownership on this date.

| Input | Terms / evidence | Release treatment |
| --- | --- | --- |
| `data/reference/sh_to_wh_ratio.csv` | Project-authored; MIT, copyright as in LICENSE | Included unchanged |
| NRW building heat demand | [Official download directory](https://www.opengeodata.nrw.de/produkte/umwelt_klima/energie/kwp/) explicitly specifies Datenlizenz Deutschland – Zero – Version 2.0 (dl-de/zero-2-0) | Excluded by maintainer choice and size (7.8 GB ZIP). Obtain the ZIP yourself and retain the accompanying metadata. Exclusion is a packaging choice, not a claim that this license prohibits redistribution. |
| `data/reference/slp_parameters.json` | Slim HEF03/HMF03 numerical input, transcribed by the chair from BDEW PDFs. Values corroborated to printed precision in BDEW/VKU/GEODE's 27 March 2026 guide, Appendix 6; full-precision origin and an explicit redistribution grant remain unverified | Bundled as default at the maintainer's request, with source/version and transcription credit. No MIT or other open-license grant for the BDEW source compilation is asserted. See [SLP provenance and setup](docs/slp-inputs.md). |
| `SLP-Gas_Pramter_Tagesfaktoren.xlsx` and additional coefficient tables | Original chair-authored workbook and other locally supplied profiles | Excluded. Keep local overrides outside the source archive. |
| Six local resource GeoPackages | Manz, Billerbeck, Fallahnejad et al., [Fraunhofer Fordatis 341.2](https://fordatis.fraunhofer.de/handle/fordatis/341.2?locale=en&mode=full), DOI 10.24406/fordatis/280.2; record specifies CC BY 4.0 | Separate resource bundle; original credits, license, local checksums and preparation notes accompany it. No GIS binaries in the source archive. |
| OpenStreetMap streets/geocoding | [ODbL 1.0](https://www.openstreetmap.org/copyright) | Acquired at runtime, caches excluded. Retain © OpenStreetMap contributors and the ODbL link. Review share-alike/database obligations when distributing derived databases; code remains MIT. |
| Open-Meteo historical weather | [CC BY 4.0 data and API terms](https://open-meteo.com/en/terms); ERA5-Land/Copernicus/ECMWF | Runtime acquisition, caches excluded. Credit Open-Meteo and the underlying source, link CC BY 4.0 and identify changes. Free API is restricted to non-commercial use; commercial users need a permitted service or self-hosting. |
| EPEX/EEX price workbooks | Provider market-data terms; no redistribution grant established | Excluded. Optional variable-price mode requires authorized local workbooks; fixed-price defaults avoid them. |
| Map tiles / search services | Provider-specific service terms, separate from underlying data licenses | Keep map attribution. Review CARTO, OSM tile-service and configured geocoder usage policies for a public deployment. |

Resource file hashes are recorded in [data-manifest.json](docs/licenses/data-manifest.json).
Do not treat that manifest as proof of copyright ownership: it identifies local
files and their reviewed source attribution. Tests use synthetic/in-memory inputs;
the Brilon characterization baseline retains aggregate model results rather than
the original building or provider tables.

Keep provider workbooks, additional local JSON coefficient tables, geodatabases, caches,
credentials and generated run results out of Git. The source exporter deliberately
includes only the ratio CSV and the slim default SLP JSON from `data/`.
Run the release audit on the exact archive.
The audit detects common credential/path patterns; it is not a guarantee that all
possible secrets or third-party content have been found.

New data needs a source URL, version, license, attribution, preparation record and
redistribution decision. Do not substitute arbitrary production coefficients to
make a demo appear complete, or mark unverified data as MIT.
