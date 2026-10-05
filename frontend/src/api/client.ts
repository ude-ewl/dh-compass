import { z } from "zod";

import type { CalculationAccepted, CalculationContract } from "./calculations";
import type { components } from "./generated-types";
import type { ComparisonResource } from "./comparison";
import type { ExportJob } from "./exports";
import type {
  ArtifactPage,
  CandidateRecord,
  CostResult,
  DecentralResult,
  IterationRecord,
  NetworkResult,
  Page,
  ResultEnvelope,
  RunManifest,
  SupplyResult,
  TimeSeriesResult,
} from "./results";
import type {
  ConfigurationSchemaResponse,
  ConfigurationValidationResponse,
  CreateProjectInput,
  CreateScenarioInput,
  Page as ProjectPage,
  ProjectDetail,
  ProjectSummary,
  RunHistory,
  ScenarioConfigMutationResponse,
  ScenarioConfigResponse,
  ScenarioSummary,
  UpdateConfigInput,
  UpdateScenarioInput,
} from "./projects";
import type {
  BoundaryInspection,
  DatasetLayerResponse,
  DatasetReadiness,
  PreviewCandidate,
  PreviewCandidateResponse,
  PreviewResource,
  RecentRunsPage,
  RunEvent,
  RunLogResponse,
  RunResource,
  StudyArea,
  ValidationIssue,
} from "./workflow";

type ApiErrorPayload = components["schemas"]["ApiError"];
type HealthResponse = components["schemas"]["HealthResponse"];

const fieldErrorSchema = z.object({
  path: z.string(),
  message: z.string(),
  code: z.string().nullable().optional(),
});

const apiErrorSchema = z.object({
  code: z.string(),
  message: z.string(),
  field_errors: z.array(fieldErrorSchema).default([]),
  details: z.record(z.unknown()).default({}),
  request_id: z.string(),
});

export type NormalizedApiError = ApiErrorPayload;

export class ApiClientError extends Error {
  readonly status: number;
  readonly payload: NormalizedApiError;

  constructor(status: number, payload: NormalizedApiError) {
    super(payload.message);
    this.name = "ApiClientError";
    this.status = status;
    this.payload = payload;
  }
}

/**
 * Network and server failures are safe to retry; validation and not-found
 * responses are not. Query hooks use this predicate so an API restart can
 * recover without replaying a submitted calculation command.
 */
export function isTransientApiError(error: unknown): boolean {
  if (!(error instanceof ApiClientError)) return false;
  return (
    error.status === 0 ||
    error.status === 408 ||
    error.status === 429 ||
    error.status >= 500
  );
}

export function shouldRetryApiRequest(
  failureCount: number,
  error: unknown,
): boolean {
  return failureCount < 3 && isTransientApiError(error);
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "/api/v1").replace(
  /\/$/,
  "",
);

function urlFor(path: string): string {
  return `${apiBaseUrl}/${path.replace(/^\//, "")}`;
}

function runPath(runId: string, suffix = ""): string {
  return `/runs/${encodeURIComponent(runId)}${suffix}`;
}

export function resolveApiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  if (apiBaseUrl.startsWith("/")) {
    return path;
  }
  return new URL(path, `${apiBaseUrl}/`).toString();
}

function fallbackError(
  status: number,
  requestId: string | null,
): NormalizedApiError {
  return {
    code: status === 404 ? "NOT_FOUND" : "HTTP_ERROR",
    message: "The API request could not be completed.",
    field_errors: [],
    details: {},
    request_id: requestId ?? "unknown",
  };
}

async function readJson(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return undefined;
  }
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(urlFor(path), { ...init, headers });
  } catch {
    // A browser-level network error has no HTTP response or request envelope.
    // Normalize it so panels can offer the same local recovery action as a
    // 5xx response and retain a stable diagnostic code.
    throw new ApiClientError(0, {
      code: "API_UNAVAILABLE",
      message: "The DH-COMPASS API could not be reached. Try again.",
      field_errors: [],
      details: {},
      request_id: "unknown",
    });
  }
  const body = await readJson(response);
  if (!response.ok) {
    const parsed = apiErrorSchema.safeParse(body);
    const payload = parsed.success
      ? parsed.data
      : fallbackError(response.status, response.headers.get("X-Request-ID"));
    throw new ApiClientError(response.status, payload);
  }
  return body as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export function getCalculationContract(): Promise<CalculationContract> {
  return request<CalculationContract>("/calculations/contract");
}

export function startCalculation(
  bbox: [number, number, number, number],
  idempotencyKey: string,
): Promise<CalculationAccepted> {
  return request<CalculationAccepted>("/calculations", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ bbox }),
  });
}

export function getRuns(page = 1, pageSize = 50): Promise<Page<RunManifest>> {
  return request<Page<RunManifest>>(
    `/runs?${new URLSearchParams({ page: String(page), page_size: String(pageSize) })}`,
  );
}

export function getRun(runId: string): Promise<RunManifest> {
  return request<RunManifest>(runPath(runId));
}

/**
 * Recent metadata-backed runs for the recovery list.
 *
 * The literal `/runs/recent` path is served by the run router; the legacy
 * read-only output discovery keeps its own `/runs` listing.
 */
export function getRecentRuns(pageSize = 50): Promise<RecentRunsPage> {
  return request<RecentRunsPage>(
    `/runs/recent?${new URLSearchParams({ page_size: String(pageSize) })}`,
  );
}

export function getResultSummary(
  runId: string,
): Promise<ResultEnvelope<Record<string, unknown>>> {
  return request<ResultEnvelope<Record<string, unknown>>>(
    runPath(runId, "/results/summary"),
  );
}

export function getResultNetwork(
  runId: string,
  layers?: string[],
): Promise<ResultEnvelope<NetworkResult>> {
  const query = layers?.length
    ? `?${new URLSearchParams({ layers: layers.join(",") })}`
    : "";
  return request<ResultEnvelope<NetworkResult>>(
    runPath(runId, `/results/network${query}`),
  );
}

export function getResultIterations(
  runId: string,
): Promise<ResultEnvelope<IterationRecord[]>> {
  return request<ResultEnvelope<IterationRecord[]>>(
    runPath(runId, "/results/iterations"),
  );
}

export function getResultCandidates(
  runId: string,
): Promise<ResultEnvelope<CandidateRecord[]>> {
  return request<ResultEnvelope<CandidateRecord[]>>(
    runPath(runId, "/results/candidates"),
  );
}

export function getResultCandidate(
  runId: string,
  candidateId: number,
): Promise<ResultEnvelope<CandidateRecord>> {
  return request<ResultEnvelope<CandidateRecord>>(
    runPath(runId, `/results/candidates/${candidateId}`),
  );
}

export function getResultSupply(
  runId: string,
): Promise<ResultEnvelope<SupplyResult>> {
  return request<ResultEnvelope<SupplyResult>>(
    runPath(runId, "/results/supply"),
  );
}

export function getResultCosts(
  runId: string,
): Promise<ResultEnvelope<CostResult>> {
  return request<ResultEnvelope<CostResult>>(runPath(runId, "/results/costs"));
}

export function getResultDecentral(
  runId: string,
): Promise<ResultEnvelope<DecentralResult>> {
  return request<ResultEnvelope<DecentralResult>>(
    runPath(runId, "/results/decentral"),
  );
}

export function getResultTimeseries(
  runId: string,
  options: { series?: string[]; resolution?: number } = {},
): Promise<ResultEnvelope<TimeSeriesResult>> {
  const query = new URLSearchParams();
  if (options.series?.length) query.set("series", options.series.join(","));
  if (options.resolution) query.set("resolution", String(options.resolution));
  const suffix = `/results/timeseries${query.toString() ? `?${query}` : ""}`;
  return request<ResultEnvelope<TimeSeriesResult>>(runPath(runId, suffix));
}

export function getArtifacts(runId: string): Promise<ArtifactPage> {
  return request<ArtifactPage>(runPath(runId, "/artifacts"));
}

export function createComparison(
  runIds: string[],
  includeUnchangedConfiguration = false,
): Promise<ComparisonResource> {
  return request<ComparisonResource>("/comparisons", {
    method: "POST",
    body: JSON.stringify({
      run_ids: runIds,
      include_unchanged_configuration: includeUnchangedConfiguration,
    }),
  });
}

export function getComparison(
  comparisonId: string,
): Promise<ComparisonResource> {
  return request<ComparisonResource>(
    `/comparisons/${encodeURIComponent(comparisonId)}`,
  );
}

export function createRunReport(runId: string): Promise<ExportJob> {
  return request<ExportJob>(runPath(runId, "/reports"), { method: "POST" });
}

export function createRunBundle(runId: string): Promise<ExportJob> {
  return request<ExportJob>(runPath(runId, "/bundles"), { method: "POST" });
}

export function createCsvExport(
  runId: string,
  table = "summary",
): Promise<ExportJob> {
  return request<ExportJob>(runPath(runId, "/exports/csv"), {
    method: "POST",
    body: JSON.stringify({ table }),
  });
}

export function getExportJob(exportId: string): Promise<ExportJob> {
  return request<ExportJob>(`/exports/${encodeURIComponent(exportId)}`);
}

export function runCsvUrl(runId: string, table: string): string {
  return resolveApiUrl(
    urlFor(runPath(runId, `/exports/${encodeURIComponent(table)}.csv`)),
  );
}

function projectPath(projectId: string, suffix = ""): string {
  return `/projects/${encodeURIComponent(projectId)}${suffix}`;
}

function scenarioPath(scenarioId: string, suffix = ""): string {
  return `/scenarios/${encodeURIComponent(scenarioId)}${suffix}`;
}

export function getProjects(
  includeArchived = false,
): Promise<ProjectPage<ProjectSummary>> {
  const query = includeArchived ? "?include_archived=true" : "";
  return request<ProjectPage<ProjectSummary>>(`/projects${query}`);
}

export function createProject(
  input: CreateProjectInput,
): Promise<ProjectSummary> {
  return request<ProjectSummary>("/projects", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getProject(projectId: string): Promise<ProjectDetail> {
  return request<ProjectDetail>(projectPath(projectId));
}

export function updateProject(
  projectId: string,
  input: { name?: string; description?: string | null },
): Promise<ProjectSummary> {
  return request<ProjectSummary>(projectPath(projectId), {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function archiveProject(projectId: string): Promise<ProjectSummary> {
  return request<ProjectSummary>(projectPath(projectId, "/archive"), {
    method: "POST",
  });
}

export function deleteProject(projectId: string): Promise<void> {
  return request<void>(projectPath(projectId), { method: "DELETE" });
}

export function getScenarios(
  projectId: string,
  includeArchived = false,
): Promise<ProjectPage<ScenarioSummary>> {
  const query = includeArchived ? "?include_archived=true" : "";
  return request<ProjectPage<ScenarioSummary>>(
    projectPath(projectId, `/scenarios${query}`),
  );
}

export function createScenario(
  projectId: string,
  input: CreateScenarioInput,
): Promise<ScenarioSummary> {
  return request<ScenarioSummary>(projectPath(projectId, "/scenarios"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getScenario(scenarioId: string): Promise<ScenarioSummary> {
  return request<ScenarioSummary>(scenarioPath(scenarioId));
}

export function updateScenario(
  scenarioId: string,
  input: UpdateScenarioInput,
): Promise<ScenarioSummary> {
  return request<ScenarioSummary>(scenarioPath(scenarioId), {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function duplicateScenario(
  scenarioId: string,
  input: { name?: string; description?: string } = {},
): Promise<ScenarioSummary> {
  return request<ScenarioSummary>(scenarioPath(scenarioId, "/duplicate"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function importScenario(
  projectId: string,
  toml: string,
  input: { name?: string; description?: string } = {},
): Promise<ScenarioSummary> {
  return request<ScenarioSummary>("/scenarios/import", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, toml, ...input }),
  });
}

export function getScenarioConfig(
  scenarioId: string,
): Promise<ScenarioConfigResponse> {
  return request<ScenarioConfigResponse>(scenarioPath(scenarioId, "/config"));
}

export function updateScenarioConfig(
  scenarioId: string,
  input: UpdateConfigInput,
): Promise<ScenarioConfigMutationResponse> {
  return request<ScenarioConfigMutationResponse>(
    scenarioPath(scenarioId, "/config"),
    {
      method: "PUT",
      body: JSON.stringify(input),
    },
  );
}

export function validateScenarioConfig(
  scenarioId: string,
  input: Record<string, unknown> | { toml: string },
  replace = false,
): Promise<ConfigurationValidationResponse> {
  const body = "toml" in input ? input : { document: input, replace };
  return request<ConfigurationValidationResponse>(
    scenarioPath(scenarioId, "/validate"),
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export function getConfigurationSchema(
  scenarioId?: string,
): Promise<ConfigurationSchemaResponse> {
  const query = scenarioId
    ? `?scenario_id=${encodeURIComponent(scenarioId)}`
    : "";
  return request<ConfigurationSchemaResponse>(`/configuration/schema${query}`);
}

export function scenarioConfigTomlUrl(scenarioId: string): string {
  return resolveApiUrl(urlFor(scenarioPath(scenarioId, "/config.toml")));
}

export function getProjectRuns(
  projectId: string,
): Promise<ProjectPage<RunHistory>> {
  return request<ProjectPage<RunHistory>>(projectPath(projectId, "/runs"));
}

export function getScenarioRuns(
  scenarioId: string,
): Promise<ProjectPage<RunHistory>> {
  return request<ProjectPage<RunHistory>>(scenarioPath(scenarioId, "/runs"));
}

export function getScenarioArea(scenarioId: string): Promise<StudyArea> {
  return request<StudyArea>(scenarioPath(scenarioId, "/area"));
}

export function updateScenarioArea(
  scenarioId: string,
  input: {
    bbox: [number, number, number, number];
    expected_revision_id?: string;
    display_geometry?: Record<string, unknown> | null;
    source?: string;
    imported_filename?: string | null;
    crs?: string | null;
  },
): Promise<StudyArea> {
  return request<StudyArea>(scenarioPath(scenarioId, "/area"), {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function inspectBoundary(
  geojson: Record<string, unknown>,
): Promise<BoundaryInspection> {
  return request<BoundaryInspection>("/boundaries/inspect", {
    method: "POST",
    body: JSON.stringify(geojson),
  });
}

export function searchGeocoding(
  query: string,
  limit = 5,
): Promise<{
  results: Array<{
    display_name: string;
    geometry: Record<string, unknown> | null;
    bbox: number[] | null;
    provider_id: string | null;
  }>;
  provider: string;
  warning: string | null;
}> {
  return request("/geocoding/search", {
    method: "POST",
    body: JSON.stringify({ query, limit }),
  });
}

export function getDatasets(scenarioId: string): Promise<DatasetReadiness> {
  return request<DatasetReadiness>(scenarioPath(scenarioId, "/datasets"));
}

export function validateDatasets(
  scenarioId: string,
  datasetIds?: string[],
): Promise<DatasetReadiness> {
  return request<DatasetReadiness>(
    scenarioPath(scenarioId, "/datasets/validate"),
    {
      method: "POST",
      body: JSON.stringify(datasetIds ? { dataset_ids: datasetIds } : {}),
    },
  );
}

export function refreshDataset(
  scenarioId: string,
  datasetId: string,
): Promise<{
  scenario_id: string;
  dataset: DatasetReadiness["datasets"][number];
  action: string;
  message: string;
}> {
  return request(
    scenarioPath(
      scenarioId,
      `/datasets/${encodeURIComponent(datasetId)}/refresh`,
    ),
    {
      method: "POST",
      body: JSON.stringify({}),
    },
  );
}

export function getDatasetLayer(
  scenarioId: string,
  datasetId: string,
): Promise<DatasetLayerResponse> {
  return request<DatasetLayerResponse>(
    scenarioPath(
      scenarioId,
      `/datasets/${encodeURIComponent(datasetId)}/layer`,
    ),
  );
}

export function createPreview(
  scenarioId: string,
  input: {
    scenario_revision_id: string;
    linear_heat_density_threshold_mwh_per_m_a?: number;
  },
): Promise<PreviewResource> {
  return request<PreviewResource>(scenarioPath(scenarioId, "/previews"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getPreview(previewId: string): Promise<PreviewResource> {
  return request<PreviewResource>(`/previews/${encodeURIComponent(previewId)}`);
}

export function cancelPreview(previewId: string): Promise<PreviewResource> {
  return request<PreviewResource>(
    `/previews/${encodeURIComponent(previewId)}/cancel`,
    {
      method: "POST",
    },
  );
}

export function createRun(
  scenarioId: string,
  input: {
    scenario_revision_id: string;
    preview_id: string;
    name?: string;
    description?: string;
    output_label?: string;
    warning_acknowledgements?: string[];
  },
  idempotencyKey?: string,
): Promise<RunResource> {
  const headers = idempotencyKey
    ? { "Idempotency-Key": idempotencyKey }
    : undefined;
  return request<RunResource>(scenarioPath(scenarioId, "/runs"), {
    method: "POST",
    headers,
    body: JSON.stringify(input),
  });
}

export function getManagedRun(runId: string): Promise<RunResource> {
  return request<RunResource>(`/runs/${encodeURIComponent(runId)}`);
}

export function cancelRun(runId: string): Promise<RunResource> {
  return request<RunResource>(`/runs/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
  });
}

export function getRunEvents(
  runId: string,
  afterSequence = 0,
): Promise<RunEvent[]> {
  return request<RunEvent[]>(
    `/runs/${encodeURIComponent(runId)}/events?after_sequence=${afterSequence}&format=json`,
  );
}

export function runEventsUrl(runId: string, afterSequence = 0): string {
  return resolveApiUrl(
    urlFor(
      `/runs/${encodeURIComponent(runId)}/events?after_sequence=${afterSequence}`,
    ),
  );
}

export function getRunLogs(runId: string): Promise<RunLogResponse> {
  return request<RunLogResponse>(`/runs/${encodeURIComponent(runId)}/logs`);
}

export function getPreviewCandidates(previewId: string): Promise<{
  preview_id: string;
  available: boolean;
  candidates: PreviewCandidate[];
  warnings: ValidationIssue[];
}> {
  return request(`/previews/${encodeURIComponent(previewId)}/candidates`);
}

export function getPreviewCandidate(
  previewId: string,
  candidateId: number,
): Promise<PreviewCandidateResponse> {
  return request<PreviewCandidateResponse>(
    `/previews/${encodeURIComponent(previewId)}/candidates/${candidateId}`,
  );
}

export function getPreviewLayer(
  previewId: string,
  layerName: string,
): Promise<import("./results").FeatureCollection> {
  return request<import("./results").FeatureCollection>(
    `/previews/${encodeURIComponent(previewId)}/layers/${encodeURIComponent(layerName)}`,
  );
}

export function artifactDownloadUrl(
  runId: string,
  artifactId: string,
  suppliedUrl?: string | null,
): string {
  if (suppliedUrl) {
    return resolveApiUrl(suppliedUrl);
  }
  return urlFor(
    runPath(runId, `/artifacts/${encodeURIComponent(artifactId)}/download`),
  );
}

export function isApiClientError(error: unknown): error is ApiClientError {
  return error instanceof ApiClientError;
}

export const api = {
  archiveProject,
  artifactDownloadUrl,
  cancelPreview,
  getCalculationContract,
  cancelRun,
  createComparison,
  createCsvExport,
  createPreview,
  createRun,
  createRunBundle,
  createRunReport,
  getComparison,
  getDatasetLayer,
  getDatasets,
  getPreview,
  getPreviewCandidate,
  getPreviewCandidates,
  getPreviewLayer,
  getManagedRun,
  getRecentRuns,
  getRunEvents,
  getRunLogs,
  getScenarioArea,
  createProject,
  createScenario,
  deleteProject,
  duplicateScenario,
  getArtifacts,
  getConfigurationSchema,
  getHealth,
  getProject,
  getProjectRuns,
  getProjects,
  getScenario,
  getScenarioConfig,
  getScenarioRuns,
  getScenarios,
  inspectBoundary,
  importScenario,
  getResultCandidate,
  getResultCandidates,
  getResultCosts,
  getResultDecentral,
  getResultIterations,
  getResultNetwork,
  getResultSummary,
  getResultSupply,
  getResultTimeseries,
  getExportJob,
  getRun,
  getRuns,
  isApiClientError,
  isTransientApiError,
  shouldRetryApiRequest,
  refreshDataset,
  request,
  runCsvUrl,
  runEventsUrl,
  searchGeocoding,
  startCalculation,
  scenarioConfigTomlUrl,
  updateProject,
  updateScenario,
  updateScenarioArea,
  updateScenarioConfig,
  validateDatasets,
  validateScenarioConfig,
};
