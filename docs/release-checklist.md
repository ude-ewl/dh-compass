# Release checklist

1. Install locked dependencies with `uv sync --locked --extra web` and run:

   ```bash
   uv run pytest
   uv run ruff check .
   ```

2. In `frontend/`, install locked dependencies and run the frontend checks:

   ```bash
   npm ci
   npm run lint
   npm run typecheck
   npm test
   npm run test:e2e
   npm run build
   npm run licenses:check
   ```

3. Generate dependency reports and inspect third-party license notices:

   ```bash
   uv run python scripts/dependency_licenses.py
   ```

   Include `frontend/dist/THIRD_PARTY_LICENSES.txt` with a distributed frontend
   build. Review native-library terms when distributing an executable,
   container, or environment.

4. Check the repository for credentials, local paths, provider data, caches,
   and generated outputs:

   ```bash
   uv run python scripts/release_audit.py
   ```

5. Build the CC BY 4.0 heat-resource bundle, if publishing it, with:

   ```bash
   uv run python scripts/export_resource_data.py
   ```

   Keep its attribution, license text, preparation notes, and checksums with
   the data.

6. Verify installation, CLI help, tests, and the frontend build from the files
   intended for publication. Production calculations still require the NRW
   building-demand data described in [`../data/README.md`](../data/README.md).

Automated checks complement rather than replace a review of dataset rights,
third-party notices, credentials, and generated artifacts.
