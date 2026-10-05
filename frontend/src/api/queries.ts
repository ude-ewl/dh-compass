import { useQuery } from "@tanstack/react-query";

import {
  getArtifacts,
  getCalculationContract,
  getComparison,
  getDatasetLayer,
  getDatasets,
  getPreview,
  getPreviewCandidates,
  getPreviewLayer,
  getConfigurationSchema,
  getHealth,
  getProject,
  getExportJob,
  getRecentRuns,
  getProjectRuns,
  getProjects,
  getScenario,
  getScenarioArea,
  getScenarioConfig,
  getScenarioRuns,
  getScenarios,
  getResultCandidate,
  getResultCandidates,
  getResultCosts,
  getResultDecentral,
  getResultIterations,
  getResultNetwork,
  getResultSummary,
  getResultSupply,
  getResultTimeseries,
  getRun,
  getRuns,
  getManagedRun,
  shouldRetryApiRequest,
} from "./client";

export function useHealthQuery() {
  return useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    retry: false,
    staleTime: 30_000,
  });
}

export function useCalculationContractQuery() {
  return useQuery({
    queryKey: ["calculation-contract"],
    queryFn: getCalculationContract,
    retry: shouldRetryApiRequest,
    retryDelay: (attempt) => Math.min(500 * 2 ** attempt, 3_000),
    staleTime: 300_000,
  });
}

export function useRunsQuery(page = 1, pageSize = 50) {
  return useQuery({
    queryKey: ["runs", { page, pageSize }],
    queryFn: () => getRuns(page, pageSize),
    retry: false,
    staleTime: 15_000,
  });
}

/**
 * Recovery list of runs started from this application.
 *
 * Polling stays enabled while a run is unfinished so a backgrounded or
 * reloaded tab keeps an accurate status line without opening a run page.
 */
export function useRecentRunsQuery(pageSize = 50) {
  return useQuery({
    queryKey: ["recent-runs", { pageSize }],
    queryFn: () => getRecentRuns(pageSize),
    retry: shouldRetryApiRequest,
    retryDelay: (attempt) => Math.min(500 * 2 ** attempt, 3_000),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      return items.some(
        (run) => !["completed", "failed", "cancelled"].includes(run.status),
      )
        ? 5_000
        : false;
    },
    staleTime: 5_000,
  });
}

export function useProjectsQuery(includeArchived = false) {
  return useQuery({
    queryKey: ["projects", { includeArchived }],
    queryFn: () => getProjects(includeArchived),
    retry: false,
    staleTime: 15_000,
  });
}

export function useProjectQuery(projectId: string | undefined) {
  return useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId ?? ""),
    enabled: Boolean(projectId),
    retry: false,
    staleTime: 15_000,
  });
}

export function useScenariosQuery(projectId: string | undefined) {
  return useQuery({
    queryKey: ["project", projectId, "scenarios"],
    queryFn: () => getScenarios(projectId ?? ""),
    enabled: Boolean(projectId),
    retry: false,
    staleTime: 15_000,
  });
}

export function useScenarioQuery(scenarioId: string | undefined) {
  return useQuery({
    queryKey: ["scenario", scenarioId],
    queryFn: () => getScenario(scenarioId ?? ""),
    enabled: Boolean(scenarioId),
    retry: false,
    staleTime: 5_000,
  });
}

export function useScenarioAreaQuery(scenarioId: string | undefined) {
  return useQuery({
    queryKey: ["scenario", scenarioId, "area"],
    queryFn: () => getScenarioArea(scenarioId ?? ""),
    enabled: Boolean(scenarioId),
    retry: false,
    staleTime: 15_000,
  });
}

export function useDatasetsQuery(scenarioId: string | undefined) {
  return useQuery({
    queryKey: ["scenario", scenarioId, "datasets"],
    queryFn: () => getDatasets(scenarioId ?? ""),
    enabled: Boolean(scenarioId),
    retry: false,
    staleTime: 5_000,
  });
}

export function useDatasetLayerQuery(
  scenarioId: string | undefined,
  datasetId: string | null,
) {
  return useQuery({
    queryKey: ["scenario", scenarioId, "dataset-layer", datasetId],
    queryFn: () => getDatasetLayer(scenarioId ?? "", datasetId ?? ""),
    enabled: Boolean(scenarioId) && Boolean(datasetId),
    retry: false,
    staleTime: 60_000,
  });
}

export function usePreviewQuery(previewId: string | undefined) {
  return useQuery({
    queryKey: ["preview", previewId],
    queryFn: () => getPreview(previewId ?? ""),
    enabled: Boolean(previewId),
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" ||
        status === "running" ||
        status === "cancellation_requested"
        ? 2_000
        : false;
    },
    staleTime: 1_000,
  });
}

export function usePreviewLayerQuery(
  previewId: string | undefined,
  layerName: string | null,
) {
  return useQuery({
    queryKey: ["preview", previewId, "layer", layerName],
    queryFn: () => getPreviewLayer(previewId ?? "", layerName ?? ""),
    enabled: Boolean(previewId) && Boolean(layerName),
    retry: false,
    staleTime: 60_000,
  });
}

export function usePreviewCandidatesQuery(previewId: string | undefined) {
  return useQuery({
    queryKey: ["preview", previewId, "candidates"],
    queryFn: () => getPreviewCandidates(previewId ?? ""),
    enabled: Boolean(previewId),
    retry: false,
    staleTime: 5_000,
  });
}

export function useScenarioConfigQuery(scenarioId: string | undefined) {
  return useQuery({
    queryKey: ["scenario", scenarioId, "config"],
    queryFn: () => getScenarioConfig(scenarioId ?? ""),
    enabled: Boolean(scenarioId),
    retry: false,
    staleTime: 5_000,
  });
}

export function useConfigurationSchemaQuery(scenarioId?: string) {
  return useQuery({
    queryKey: ["configuration-schema", scenarioId ?? null],
    queryFn: () => getConfigurationSchema(scenarioId),
    retry: false,
    staleTime: scenarioId ? 5_000 : 300_000,
  });
}

export function useProjectRunsQuery(projectId: string | undefined) {
  return useQuery({
    queryKey: ["project", projectId, "runs"],
    queryFn: () => getProjectRuns(projectId ?? ""),
    enabled: Boolean(projectId),
    retry: false,
    staleTime: 15_000,
  });
}

export function useScenarioRunsQuery(scenarioId: string | undefined) {
  return useQuery({
    queryKey: ["scenario", scenarioId, "runs"],
    queryFn: () => getScenarioRuns(scenarioId ?? ""),
    enabled: Boolean(scenarioId),
    retry: false,
    staleTime: 15_000,
  });
}

export function useRunQuery(runId: string | undefined) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRun(runId ?? ""),
    enabled: Boolean(runId),
    retry: shouldRetryApiRequest,
    retryDelay: (attempt) => Math.min(500 * 2 ** attempt, 3_000),
    staleTime: 30_000,
  });
}

export function useManagedRunQuery(runId: string | undefined) {
  return useQuery({
    queryKey: ["managed-run", runId],
    queryFn: () => getManagedRun(runId ?? ""),
    enabled: Boolean(runId),
    retry: shouldRetryApiRequest,
    retryDelay: (attempt) => Math.min(500 * 2 ** attempt, 3_000),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && !["completed", "failed", "cancelled"].includes(status)
        ? 2_000
        : false;
    },
    staleTime: 1_000,
  });
}

export function useResultSummaryQuery(runId: string | undefined) {
  return useQuery({
    queryKey: ["result", runId, "summary"],
    queryFn: () => getResultSummary(runId ?? ""),
    enabled: Boolean(runId),
    retry: false,
    staleTime: 60_000,
  });
}

export function useResultNetworkQuery(
  runId: string | undefined,
  layers?: string[],
) {
  const requestedLayers = layers ? [...layers].sort() : undefined;
  return useQuery({
    queryKey: ["result", runId, "network", requestedLayers],
    queryFn: () => getResultNetwork(runId ?? "", requestedLayers),
    enabled: Boolean(runId),
    retry: false,
    staleTime: 60_000,
  });
}

export function useResultIterationsQuery(runId: string | undefined) {
  return useQuery({
    queryKey: ["result", runId, "iterations"],
    queryFn: () => getResultIterations(runId ?? ""),
    enabled: Boolean(runId),
    retry: false,
    staleTime: 60_000,
  });
}

export function useResultCandidatesQuery(runId: string | undefined) {
  return useQuery({
    queryKey: ["result", runId, "candidates"],
    queryFn: () => getResultCandidates(runId ?? ""),
    enabled: Boolean(runId),
    retry: false,
    staleTime: 60_000,
  });
}

export function useResultCandidateQuery(
  runId: string | undefined,
  candidateId: number | null,
) {
  return useQuery({
    queryKey: ["result", runId, "candidate", candidateId],
    queryFn: () => getResultCandidate(runId ?? "", candidateId ?? 0),
    enabled: Boolean(runId) && candidateId !== null,
    retry: false,
    staleTime: 60_000,
  });
}

export function useResultSupplyQuery(runId: string | undefined) {
  return useQuery({
    queryKey: ["result", runId, "supply"],
    queryFn: () => getResultSupply(runId ?? ""),
    enabled: Boolean(runId),
    retry: false,
    staleTime: 60_000,
  });
}

export function useResultCostsQuery(runId: string | undefined) {
  return useQuery({
    queryKey: ["result", runId, "costs"],
    queryFn: () => getResultCosts(runId ?? ""),
    enabled: Boolean(runId),
    retry: false,
    staleTime: 60_000,
  });
}

export function useResultDecentralQuery(runId: string | undefined) {
  return useQuery({
    queryKey: ["result", runId, "decentral"],
    queryFn: () => getResultDecentral(runId ?? ""),
    enabled: Boolean(runId),
    retry: false,
    staleTime: 60_000,
  });
}

export function useResultTimeseriesQuery(
  runId: string | undefined,
  enabled = false,
  options: { series?: string[]; resolution?: number } = {},
) {
  return useQuery({
    queryKey: ["result", runId, "timeseries", options],
    queryFn: () => getResultTimeseries(runId ?? "", options),
    enabled: Boolean(runId) && enabled,
    retry: false,
    staleTime: 60_000,
  });
}

export function useArtifactsQuery(runId: string | undefined) {
  return useQuery({
    queryKey: ["result", runId, "artifacts"],
    queryFn: () => getArtifacts(runId ?? ""),
    enabled: Boolean(runId),
    retry: false,
    staleTime: 60_000,
  });
}

export function useComparisonQuery(comparisonId: string | undefined) {
  return useQuery({
    queryKey: ["comparison", comparisonId],
    queryFn: () => getComparison(comparisonId ?? ""),
    enabled: Boolean(comparisonId),
    retry: false,
    staleTime: 60_000,
  });
}

export function useExportJobQuery(exportId: string | undefined) {
  return useQuery({
    queryKey: ["export", exportId],
    queryFn: () => getExportJob(exportId ?? ""),
    enabled: Boolean(exportId),
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 1_000 : false;
    },
    staleTime: 1_000,
  });
}
