# Preparation and verification

On 5 October 2026 the six prepared local files were compared against downloads
from the pinned [Fordatis 341.2 record](https://fordatis.fraunhofer.de/handle/fordatis/341.2).

| Prepared file | Relationship to original | Feature count |
| --- | --- | --- |
| `biomass_nuts2(1).gpkg` | Byte-identical to `biomass_nuts2.gpkg`; filename differs | 236 |
| `industrial_eh.gpkg` | Byte-identical | 1,639 |
| `rivers_lakes.gpkg` | Byte-identical | 652 |
| `wte.gpkg` | Byte-identical | 408 |
| `wwtp.gpkg` | Exact feature/attribute subset of published `wwtp.gpkg` | 23,730 of 24,067 |
| `hydrothermal_85_nrw.gpkg` | Exact feature/attribute subset of published `hydrothermal_85.gpkg` | 8,238 of 473,595 |

All files retain EPSG:3035. For the two subsets, every local feature's geometry
(WKB) and all published attribute columns were matched to an upstream feature.
The historical filter commands are unavailable; no particular exclusion or
clipping rule is asserted. Consumers can reproduce the released inputs exactly
from this checksum-pinned bundle, or explicitly document their own new subsets.
No attribute values or geometries were changed during this release preparation.

Original download SHA256 values for the subset sources:

- `wwtp.gpkg`: `e590b617126d3733fcb87d49f7c9989450436eaf845ef41e59e8324b4661295c`
- `hydrothermal_85.gpkg`: `d74fa25c16bb7e8ffd5d823a15054a32db51e5265d2566eaca95d03f82977f64`

The local `data-manifest.json` and SHA256SUMS.txt identify the prepared files.
Keep attribution and modification descriptions when redistributing subsets.
