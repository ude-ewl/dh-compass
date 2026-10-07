# DH-COMPASS frontend

The application currently supports **NRW only**. Help explains usage and links to configuration. The normal form uses server-owned model defaults.

The default workspace provides a dark map, a compact iteration timeline and
statistics bar, and a right-hand subgraph inspector.
Select a study area on the map and start a calculation from the side panel.
During optimization, gray subgraphs are pending, yellow is the active evaluation,
green subgraphs and paths belong to the accepted grid, and red subgraphs are
rejected. Follow live keeps the timeline at the newest reported state; scrubbing
history pauses that following until Follow live is selected again. Completed
runs use the same viewer to replay their recorded decisions.

Live geometry is reported at candidate evaluation boundaries, rather than inside
individual solver iterations. The optimizer emits complete candidate edge
collections, accepted connecting paths, marginal costs, and accepted cumulative
cost/demand through the durable run event stream. New runs include all
pending candidate edges in their first candidate-started event. Older runs can
still use the smaller provisional geometry stored in their event history.

Maps use the [OpenFreeMap dark style](https://github.com/hyperknot/openfreemap-styles).
The accessible geometry view and coordinate controls remain available when the
basemap or WebGL is unavailable.

The frontend is a Vite/React client of the versioned FastAPI API. It uses a
configurable API base URL and does not assume that the repository is the
process working directory.

## Development

From the repository root, install the optional API dependencies and start the
API in one terminal:

```bash
uv sync --extra web
uv run uvicorn dh_compass.web.app:create_app --factory --reload
```

Start the frontend in a second terminal:

```bash
cd frontend
npm install
npx playwright install chromium # required once for browser end-to-end tests
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000` by default. Set
`VITE_API_PROXY_TARGET` to use another development API. For a separately hosted
API, set `VITE_API_BASE_URL` to its `/api/v1` base URL.

The constrained area → calculation → result workspace is the default. Project,
scenario, comparison, and expert workflow routes redirect to the area workspace.
Legacy routes can be enabled with:

```bash
VITE_DH_COMPASS_FRONTEND_LEGACY_ROUTES=true npm run dev
```

For a full rollback deployment only, set
`VITE_DH_COMPASS_FRONTEND_REDESIGN=false` when building or starting Vite and
`DH_COMPASS_WEB_FRONTEND_REDESIGN=false` for an accurate system-status flag.

## Quality checks

```bash
npm run lint
npm run typecheck
npm test
npm run test:e2e
npm run test:e2e:legacy
npm run openapi:check
```

When the API is running, refresh the checked-in OpenAPI TypeScript snapshot:

```bash
npm run openapi:types
```

The production build is written to `frontend/dist`, which the default web
settings use when it exists. The build also emits
`dh-compass-frontend.json`; the API checks this manifest against its own
version at startup. When building for a different API release, set
`VITE_DH_COMPASS_API_VERSION` explicitly:

```bash
VITE_DH_COMPASS_API_VERSION=0.1.0 npm run build
```

Set `DH_COMPASS_WEB_FRONTEND_STATIC_PATH` to serve a differently located
compiled single-page application. The packaged Python distribution includes
package-data support for a copied `dh_compass.web/static` build, but the
supported repository/deployment workflow is to build `frontend/dist` in the
release job and configure this path explicitly.

For the complete local application use:

```bash
cd ..
uv run dh-compass web --host 127.0.0.1 --port 8000 --open-browser
```

## Runs, Help and languages

`/recent` restores accepted calculations and discovers completed output folders. `/runs/:runId` combines progress, map playback and final combined results; Inputs & downloads opens provenance and available files. Older result tabs are compatibility views.

`/help` explains the tool, NRW scope, workflow and result units with GitHub/configuration/methodology links. English/Deutsch is available in desktop/mobile headers. `src/i18n/locale.ts` subscribes components without remounting, persists `dh-compass:language` and updates document language. German messages live in `de.ts`; helpers in `translate.ts` and `messages.ts`. Dates/numbers follow the locale; inputs, API payloads, logs and artifact content are preserved.

Provide both language variants for new labels and test live switching, persisted preference, accessibility and retained form state. See [operations](../docs/frontend/operations.md) and [technical architecture](../docs/frontend/technical-architecture.md).
