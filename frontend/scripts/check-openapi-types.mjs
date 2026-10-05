import { readFile } from "node:fs/promises";

const generatedPath = new URL("../src/api/generated-types.ts", import.meta.url);
const generated = await readFile(generatedPath, "utf8");

const requiredPaths = [
  '"/api/v1/health"',
  '"/api/v1/calculations/contract"',
  '"/api/v1/calculations"',
  '"/api/v1/system/status"',
  '"/api/v1/runs"',
  '"/api/v1/runs/recent"',
  '"/api/v1/runs/{run_id}/results/summary"',
  '"/api/v1/runs/{run_id}/results/network"',
  '"/api/v1/runs/{run_id}/artifacts/{artifact_id}/download"',
];
const requiredSchemas = [
  "HealthResponse",
  "CalculationContractResponse",
  "StartupStatusResponse",
  "ApiError",
  "RunManifest",
  "RunSummaryListResponse",
  "ResultEnvelope",
];

if (
  requiredPaths.some((path) => !generated.includes(path)) ||
  requiredSchemas.some((schema) => !generated.includes(schema))
) {
  throw new Error(
    "Generated OpenAPI types do not contain the current web contract. Run npm run openapi:types.",
  );
}

console.log("OpenAPI type snapshot contains the required frontend contract.");
