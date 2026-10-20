# Data licenses and distribution

The project's MIT license covers project code, documentation, and the
project-authored ratio CSV. It does not relicense third-party data.

| Input | Terms / source | Repository availability |
| --- | --- | --- |
| `data/reference/sh_to_wh_ratio.csv` | Project-authored; MIT, copyright as in `LICENSE` | Included |
| NRW building heat demand | The [official download directory](https://www.opengeodata.nrw.de/produkte/umwelt_klima/energie/kwp/) specifies Datenlizenz Deutschland – Zero – Version 2.0 (dl-de/zero-2-0) | Download separately and retain the accompanying metadata. |
| `data/reference/slp_parameters.json` | HEF03/HMF03 numerical input transcribed by the Chair of Energy Economics from BDEW publications. Values are corroborated to printed precision in BDEW/VKU/GEODE's 27 March 2026 guide, Appendix 6. | Included with source/version and transcription credit. No open-license grant for the underlying BDEW compilation is asserted. See [SLP provenance and setup](docs/slp-inputs.md). |
| Additional SLP coefficient tables | Terms depend on the selected provider and publication. | Supply authorized local JSON or workbook overrides; do not commit them unless redistribution is permitted. |
| VG250-EW municipal population/boundaries | [BKG VG250-EW, 31 December 2024](https://daten.gdz.bkg.bund.de/produkte/vg/vg250-ew_ebenen_1231/2024/); [dl-de/by-2-0](https://www.govdata.de/dl-de/by-2-0) | Supplied/downloaded locally, not redistributed with code or the Fordatis bundle. Retain © BKG, acquisition/access year, source and underlying data-source links, and NRW filtering/normalization notes. [Preparation](docs/biomass-allocation.md), [checksum record](docs/licenses/biomass-population-manifest.json). |
| Six heat-resource GeoPackages | Manz, Billerbeck, Fallahnejad et al., [Fraunhofer Fordatis 341.2](https://fordatis.fraunhofer.de/handle/fordatis/341.2?locale=en&mode=full), DOI 10.24406/fordatis/280.2; CC BY 4.0 | Available as a separate resource bundle with attribution, license, checksums, and preparation notes. |
| OpenStreetMap streets/geocoding | [ODbL 1.0](https://www.openstreetmap.org/copyright) | Acquired at runtime. Retain © OpenStreetMap contributors and the ODbL link, and review database obligations when distributing derived data. |
| Open-Meteo historical weather | [CC BY 4.0 data and API terms](https://open-meteo.com/en/terms); ERA5-Land/Copernicus/ECMWF | Acquired at runtime. Credit Open-Meteo and the underlying source. The free API is restricted to non-commercial use; commercial users need a permitted service or self-hosting. |
| Map tiles and search services | Provider-specific service terms, separate from underlying data licenses | Keep required map attribution and review the policies of configured services before public deployment. |

Resource file hashes are recorded in
[`docs/licenses/data-manifest.json`](docs/licenses/data-manifest.json). The
manifest identifies files and source attribution; it is not proof of copyright
ownership.

Keep provider workbooks, local coefficient tables, geodatabases, caches,
credentials, and generated results out of Git unless their terms explicitly
permit distribution. New datasets should document their source URL, version,
license, attribution, preparation steps, and redistribution terms.
