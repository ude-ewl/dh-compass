# Running the browser application

From the source checkout, install `uv sync --locked --extra web`, then run
`npm ci` and `npm run build` in `frontend/`. Start
`uv run dh-compass web --open-browser`. Keep your data in the paths described by
`data/README.md`; the application checks data readiness before calculation.

The service is intended for a local trusted environment. Before exposing it
publicly, configure access control and hosting, provider service terms, resource
limits and persistent storage. MIT code licensing does not authorize commercial
use of Open-Meteo's free API. See DATA_LICENSES.md for service/data distinctions.

Back up the configured database and outputs together while jobs are stopped.
Retain configuration and provider provenance for reproducible runs. To update,
stop jobs, back up state, install the new locked dependencies, rebuild frontend
assets with their third-party notices, run tests and restart the service.

For development run `uv run uvicorn dh_compass.web.app:create_app --factory --reload`
and `npm run dev` in a separate terminal. A separately deployed frontend can be
selected with `DH_COMPASS_WEB_FRONTEND_STATIC_PATH`.
