# Initial source release review — 5 October 2026

The release source contains 352 files, approximately 4 MB uncompressed and
1 MB as a ZIP. The separate six-layer resource ZIP is approximately 4.2 MB.
Neither archive contains the NRW building GDB or BDEW workbook. Source archives
also exclude environments, caches, outputs and built frontend assets.

## Cleanup and licensing

- Removed unused Plotly, two ad hoc debug scripts and a 130 KB generated
  configuration listing whose source-citation fields were empty.
- Moved test-only HTTPX out of production web dependencies, removed unused
  Uvicorn extras, and declared directly imported pyogrio/pyproj dependencies.
- Retained runtime modules, supported compatibility routes, characterization
  tests, scenarios, lockfiles and the maintainer-confirmed MIT ratio table.
- Restored missing data-rights, contributing, release, operations and metric
  documentation; repaired broken local documentation links.
- Added Git-independent source export, explicit source-file selection,
  credential/provider-data auditing and deterministic ZIP checksums.
- Verified four resource layers byte-for-byte against Fordatis 341.2; verified
  geothermal and wastewater layers as exact geometry/attribute subsets. Their
  separate bundle includes CC BY 4.0 legal text, credits and preparation notes.
- Inventoried installed Python and npm licenses. Frontend builds require full
  runtime license/NOTICE texts. CBC/HiGHS wrapper wheels lacking complete notice
  entries are not redistributed; binary bundling requires further review.

## SLP usability

The maintainer subsequently confirmed that the workbook was transcribed by the
chair from BDEW PDFs, rather than downloaded as a BDEW Excel file. The 27 March
2026 guide corroborates HEF03/HMF03 values to printed precision; full-precision
provenance and the redistribution basis remain unverified. The local workbook
remains external. At the maintainer's request, the code now uses the slim
attributed HEF03/HMF03 JSON by default, preserving the original coefficient
precision and weekday factors. The JSON is included in the source archive.
A versioned JSON schema and converter allow authorized sources
to be adapted without relying on that filename. Runtime/readiness validate the
configured profiles. Default HEF/HMF conversion was verified locally.
Identical historical duplicate rows are collapsed; malformed unused GHD entries
are never guessed or repaired. See [SLP inputs](slp-inputs.md).

## Validation

- A fresh extracted source folder, with no local provider inputs, installed from
  the lockfile on Python 3.10 after adopting bundled JSON: 230 tests passed;
  Ruff passed.
- After adopting bundled JSON, Python 3.12 release environment: 230 tests passed;
  Ruff passed. HEF03/HMF03 generated profiles were compared with the original
  local workbook without changing coefficients: maximum hourly difference was
  zero for both profiles.
- Frontend unit suite, type checking, build, runtime notices and OpenAPI snapshot
  checks passed. Eight Chromium browser tests passed. ESLint has two existing
  Fast Refresh warnings and no errors; Vite reports large existing chunks.
- Source and exact source ZIP audits: 352 files, zero findings. Six resource-file
  hashes, archive checksums and required resource notices verified.
- All checked local Markdown links resolve. GitHub CI covers Python 3.10/3.12
  and frontend checks; hosted CI itself has not run because nothing was published.

A full solver-backed production scenario was not rerun: this review validates
source installation, input compatibility, packaging and tests. No Git metadata
was available, so no old commit history was reviewed or transferred. Publish the
extracted source as a fresh repository and the resource ZIP as a release asset.
