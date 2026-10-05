# Third-party components

DH-COMPASS code is MIT, copyright (c) 2026 Chair of Energy Economics,
Universität Duisburg-Essen. Dependency and provider licenses are independent.
This source release vendors no Python/npm package implementations or solver binaries.

## Python

Direct dependencies are used by application imports, data readers or the solver
boundary. Plotly was unused and removed. The installed lockfile inventory and
wheel notice-file status are recorded in docs/licenses/dependency-inventory.json.
Use scripts/dependency_licenses.py to regenerate local reports and full installed
license/NOTICE texts in outputs/license-reports/.

| Component | Declared license family |
| --- | --- |
| GeoPandas, NetworkX, NumPy, numpy-financial, pandas, scikit-learn, Shapely | BSD / permissive; NumPy includes additional bundled notices |
| holidays, openpyxl, OSMnx, pyogrio, pyproj | MIT |
| Matplotlib | Matplotlib/PSF-style license; retain full installed license |
| requests | Apache-2.0 |
| tomli (Python < 3.11) | MIT |
| Python-MIP and CBC | EPL-2.0 |
| HiGHS / highspy / highsbox | MIT; binary bundles contain additional native components |
| FastAPI, Pydantic, SQLAlchemy | MIT |
| httpx, Uvicorn, Starlette | BSD-3-Clause |
| certifi (transitive) | MPL-2.0 |

Open-source dependency licensing does not transfer their copyright to this project.
Retain copyright, license and NOTICE texts when distributing installed packages.
EPL/MPL components have source-availability obligations for covered redistributed
code; native GEOS, GDAL, PROJ, BLAS, compiler runtime and SuiteSparse components
must be reviewed under their own terms when bundling an environment. Package-level
SPDX metadata alone is insufficient for a frozen executable or container image.

The reviewed Windows cbcbox 2.935 and highsbox 1.13.1 wheels omit complete
license-file entries. They are downloaded from upstream during installation,
not included in this release. Do not redistribute those wheels or a bundled
runtime until their solver/native notices and corresponding-source obligations
are resolved. --strict-binaries on the inventory command enforces this gate.
CBC is a transitive Python-MIP dependency even though this application's automatic
fallback uses HiGHS. Gurobi is proprietary, optional and separately licensed.

## Browser dependencies

The frontend uses React, MUI, Emotion, TanStack Query, MapLibre GL JS, ECharts,
React Hook Form, React Router and Zod. Their lockfile declarations include MIT,
BSD, Apache-2.0 and ISC components. 
pm run build writes full runtime license
and NOTICE texts to dist/THIRD_PARTY_LICENSES.txt and fails if required texts
are missing. Ship that file with every compiled frontend; source releases exclude
the compiled bundle and node_modules. Dev-tool licenses are inventoried separately
by their dev lockfile flag. A conservative runtime inventory may include packages
that were tree-shaken out of the final chunks.

The compatibility HTML viewer loads Leaflet 1.9.4 (BSD-2-Clause, Volodymyr
Agafonkin / CloudMade) and Chart.js 4.4.0 (MIT, Chart.js Contributors) from CDNs.
It does not vendor them. Their original licenses are available at
https://github.com/Leaflet/Leaflet/blob/v1.9.4/LICENSE and
https://github.com/chartjs/Chart.js/blob/v4.4.0/LICENSE.md.
Preserve those notices if vendoring CDN assets later.

MapLibre loads the OpenFreeMap style/service; see https://openfreemap.org/ for
its service terms and required OpenMapTiles/OpenStreetMap attribution. MapLibre's
attribution control remains enabled. Legacy CARTO tiles retain CARTO/OSM credit.
Service usage terms are separate from npm library licenses.

See [DATA_LICENSES.md](DATA_LICENSES.md) for data, weather and output rights.
