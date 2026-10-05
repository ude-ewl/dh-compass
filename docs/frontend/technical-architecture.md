# Browser architecture

React/TypeScript and Vite provide the client in `frontend/`. The released route
graph starts with an NRW area selection, submits a calculation, follows progress
and displays final combined results. FastAPI in `src/dh_compass/web/` validates
requests, persists state and starts jobs around the same Python pipeline as the CLI.

The API types are generated in `frontend/src/api/generated-types.ts`. Result
presentation semantics live in `frontend/src/features/results/metricContract.ts`.
English/German presentation subscribes through `useLocale()`; locale changes must
preserve map state, input values and active calculations. See `frontend/README.md`
for development commands and [operations](operations.md) for startup.
