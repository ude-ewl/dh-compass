# Release checklist

The source is a small application repository, not a data mirror or an installed
environment. The code and project ratio CSV are MIT; provider terms remain
separate. Copyright holder and MIT release were confirmed by the maintainer on
5 October 2026. No source history was available in this working folder.

1. Install from the lockfiles: `uv sync --locked --extra web`; in `frontend/`,
   run `npm ci`. Run `uv run pytest` and `uv run ruff check .`.
   The default development group includes the web test dependencies so a plain
   `uv run pytest` can collect the entire suite. Production installs can use
   `uv sync --locked --no-dev` (and `--extra web` for the browser server).
2. In `frontend/`, run lint, typecheck, test, test:e2e, build and licenses:check.
   Ship `THIRD_PARTY_LICENSES.txt` with any compiled frontend. It contains full
   runtime dependency license/NOTICE texts. Source releases exclude `dist/`.
3. Run `uv run python scripts/dependency_licenses.py`. Review installed Python
   versions and npm lock entries in `outputs/license-reports/`. Native libraries
   may have terms beyond the wrapper package's declared SPDX license.
4. Run `uv run python scripts/release_audit.py` and
   `uv run python scripts/export_source.py`, then audit the exact ZIP:
   `uv run python scripts/release_audit.py --archive outputs/release/DH-COMPASS-source.zip`.
   Review the ZIP file list; only the slim default SLP JSON is allowed, with no
   original SLP workbook or extra coefficient files, NRW GDB, market data, secrets,
   runtime dependencies, local paths or output artifacts should appear.
5. Build the separately licensed resource data with
   `uv run python scripts/export_resource_data.py`; retain its attribution,
   full CC BY 4.0 legal text, preparation notes and checksums with the ZIP.
   This data ZIP intentionally has a different boundary from the source audit.
6. Extract the source ZIP into a new folder and verify installation, CLI help,
   tests, and frontend build there. Production runs still need NRW building demand.
   Default SLP coefficients are bundled; other profiles need a local input override.
7. Create the GitHub repository from the extracted source, with a fresh history.
   Add the source files only, review `git diff --cached --stat`, run the audit,
   and commit. Attach the resource ZIP as a release asset rather than Git data.
   The source ZIP must not be copied into its own Git repository.

The explicit source allowlist is in `scripts/release_files.py`. When adding a new
source format or directory, update it and verify the exported contents. Existing
tracked files are audited too, so `.gitignore` cannot hide a staged provider file.
No heuristic scan can establish authorship or identify every possible secret.

Changes made for the initial release removed unused Plotly, two ad hoc debug
scripts and a generated configuration listing with no source citations. Runtime
modules, tests, supported workflow compatibility, scenarios, lockfiles, the ratio
table and useful developer commands were retained.
