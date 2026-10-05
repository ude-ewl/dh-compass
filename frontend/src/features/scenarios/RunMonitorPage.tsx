import { tr } from "../../i18n/translate";

import { useLocale } from "../../i18n/locale";

import {
  Alert,
  Box,
  Button,
  Chip,
  Collapse,
  Divider,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from "@mui/material";

import { useMutation, useQuery } from "@tanstack/react-query";

import { useEffect, useRef, useState } from "react";

import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";

import {
  cancelRun,
  getRunEvents,
  getRunLogs,
  resolveApiUrl,
  runEventsUrl,
} from "../../api/client";

import { useManagedRunQuery } from "../../api/queries";

import type { FeatureCollection, GeoJsonFeature } from "../../api/results";

import type { RunEvent, RunResource } from "../../api/workflow";

import {
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";

import { formatDate } from "../results/format";

import { ResultMap } from "../results/ResultMap";

const stageLabels: Record<string, string> = {
  checking_input_data: "Checking input data",

  preparing_area: "Preparing area",

  finding_candidates: "Finding candidates",

  optimizing_network: "Optimizing network",

  preparing_results: "Preparing results",

  starting: "Starting worker",

  load_inputs: "Load inputs",

  prepare_geospatial_data: "Prepare geospatial data",

  assess_heat_resources: "Assess heat resources",

  build_optimization_context: "Build optimization context",

  optimize_heat_grid: "Optimize candidates",

  write_outputs: "Generate reports",

  complete: "Complete",

  cancelled: "Cancelled",

  failed: "Failed",
};

const eventNames = [
  "job.status_changed",

  "pipeline.stage_started",

  "pipeline.stage_completed",

  "optimization.candidate_started",

  "optimization.candidate_completed",

  "artifact.created",

  "job.warning",

  "job.failed",

  "heartbeat",
];

export function RunMonitorPage() {
  useLocale();

  const { runId } = useParams();

  const run = useManagedRunQuery(runId);

  const [events, setEvents] = useState<RunEvent[]>([]);

  const [showLogs, setShowLogs] = useState(false);

  const navigate = useNavigate();

  const cancelMutation = useMutation({
    mutationFn: () => cancelRun(runId ?? ""),

    onSuccess: () => void run.refetch(),
  });

  const logs = useQuery({
    queryKey: ["managed-run", runId, "logs"],

    queryFn: () => getRunLogs(runId ?? ""),

    enabled: Boolean(runId) && showLogs,

    retry: false,
  });

  useRunEventStream(runId, setEvents);

  if (!runId)
    return <FailureState error={new Error("The run identifier is missing.")} />;

  if (run.isPending)
    return <LoadingState label={tr("Restoring run monitor…")} />;

  if (run.isError) {
    return (
      <FailureState error={run.error} onRetry={() => void run.refetch()} />
    );
  }

  if (!run.data)
    return <FailureState error={new Error("The run is unavailable.")} />;

  const resource = run.data;

  const fraction = resource.progress?.fraction ?? 0;

  const active = !["completed", "failed", "cancelled"].includes(
    resource.status,
  );

  const candidate = resource.candidate_progress;

  const failureIssues = extractFailureIssues(resource.failure_details);

  return (
    <Stack spacing={3}>
      <Stack
        alignItems={{ sm: "center" }}

        direction={{ sm: "row", xs: "column" }}

        justifyContent="space-between"

        spacing={2}
      >
        <Box>
          <Typography component="h1" variant="h4">
            {tr(resource.name)}
          </Typography>

          <Typography color="text.secondary">
            {tr("Run monitor · revision ")}
            {tr(resource.scenario_revision_id.slice(0, 8))} ·{tr(" ")}
            {tr(
              resource.started_at ? formatDate(resource.started_at) : "Queued",
            )}
          </Typography>

          {resource.bbox && (
            <Typography color="text.secondary" variant="body2">
              {tr("Study area:")}

              {tr(" ")}

              {tr(resource.bbox.map((value) => value.toFixed(6)).join(", "))}
            </Typography>
          )}
        </Box>

        <Stack direction="row" spacing={1}>
          <Chip
            color={statusColor(resource.status)}

            label={tr(resource.status)}
          />

          {active && (
            <Button
              color="warning"

              disabled={
                cancelMutation.isPending ||
                resource.status === "cancellation_requested"
              }

              onClick={() => {
                if (window.confirm("Request cancellation of this run?")) {
                  cancelMutation.mutate();
                }
              }}

              variant="outlined"
            >
              {tr(
                resource.status === "cancellation_requested"
                  ? "Cancellation requested"
                  : "Cancel run",
              )}
            </Button>
          )}
        </Stack>
      </Stack>

      {resource.status === "cancellation_requested" && (
        <Alert severity="info">
          {tr(
            "Cancellation was requested. The active solver may finish its current safe operation before the worker reports Cancelled.",
          )}
        </Alert>
      )}

      {resource.failure_summary && (
        <Alert severity="error">
          <Typography fontWeight={600}>
            {tr("The run did not complete.")}
          </Typography>

          <Typography variant="body2">
            {tr(resource.failure_summary)}
          </Typography>

          {Boolean(resource.failure_details.code) && (
            <Typography variant="caption">
              {tr("Diagnostic code: ")}

              {tr(String(resource.failure_details.code))}
            </Typography>
          )}

          {failureIssues.length > 0 && (
            <Box component="ul" sx={{ mb: 0, mt: 1, pl: 2.5 }}>
              {failureIssues.map((issue) => (
                <li key={`${issue.message}:${issue.remediation ?? ""}`}>
                  <Typography variant="body2">
                    {tr(issue.message)}

                    {tr(issue.remediation ? ` ${issue.remediation}` : "")}
                  </Typography>
                </li>
              ))}
            </Box>
          )}
        </Alert>
      )}

      {cancelMutation.isError && <FailureState error={cancelMutation.error} />}

      <Paper component="section" sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Stack direction="row" justifyContent="space-between" spacing={2}>
            <Typography component="h2" variant="h6">
              {tr("Progress")}
            </Typography>

            <Typography color="text.secondary" variant="body2">
              {tr(
                stageLabels[resource.stage ?? ""] ?? resource.stage ?? "Queued",
              )}
            </Typography>
          </Stack>

          <LinearProgress
            aria-label={tr("Run progress")}

            value={Math.max(0, Math.min(100, fraction * 100))}

            variant={
              resource.progress?.fraction === null ||
              resource.progress?.fraction === undefined
                ? "indeterminate"
                : "determinate"
            }
          />

          <StageTimeline current={resource.stage} status={resource.status} />

          {candidate && (
            <Paper component="section" variant="outlined" sx={{ p: 2 }}>
              <Typography component="h3" gutterBottom variant="subtitle1">
                {tr("Candidate optimization")}
              </Typography>

              <Stack direction={{ sm: "row", xs: "column" }} spacing={3}>
                <Metric
                  label={tr("Completed")}

                  value={`${candidate.completed_candidates} / ${candidate.total_candidates ?? "—"}`}
                />

                <Metric
                  label={tr("Connected")}

                  value={String(candidate.connected_candidates)}
                />

                <Metric
                  label={tr("Rejected")}

                  value={String(candidate.rejected_candidates)}
                />

                <Metric
                  label={tr("Current")}

                  value={
                    candidate.current_candidate_id === null
                      ? "—"
                      : String(candidate.current_candidate_id)
                  }
                />
              </Stack>
            </Paper>
          )}

          <Typography color="text.secondary" variant="body2">
            {tr("Heartbeat:")}

            {tr(" ")}

            {tr(
              resource.process_identity?.heartbeat_at
                ? formatDate(resource.process_identity.heartbeat_at)
                : "Waiting for worker",
            )}
          </Typography>
        </Stack>
      </Paper>

      <ProvisionalRunMap events={events} />

      <Paper component="section" sx={{ p: 3 }}>
        <Typography component="h2" gutterBottom variant="h6">
          {tr("Event feed")}
        </Typography>

        {events.length === 0 ? (
          <Typography color="text.secondary">
            {tr(
              "No live events have arrived yet. Status polling remains authoritative.",
            )}
          </Typography>
        ) : (
          <Stack divider={<Divider flexItem />} spacing={1}>
            {events.slice(-40).map((event) => (
              <Stack
                key={`${event.sequence}-${event.id}`}

                direction={{ sm: "row", xs: "column" }}

                spacing={1}
              >
                <Typography
                  color="text.secondary"

                  sx={{ minWidth: 70 }}

                  variant="caption"
                >
                  #{tr(event.sequence)}
                </Typography>

                <Typography variant="body2">
                  {tr(plainLanguageEvent(event))}
                </Typography>
              </Stack>
            ))}
          </Stack>
        )}
      </Paper>

      <Paper component="section" sx={{ p: 3 }}>
        <Stack spacing={1}>
          <Stack
            alignItems="center"

            direction={{ sm: "row", xs: "column" }}

            justifyContent="space-between"

            spacing={1}
          >
            <Typography component="h2" variant="h6">
              {tr("Technical logs")}
            </Typography>

            <Stack direction="row" spacing={1}>
              {resource.log_url && (
                <Button
                  component="a"

                  href={resolveApiUrl(resource.log_url)}

                  size="small"

                  target="_blank"
                >
                  {tr("Download diagnostics")}
                </Button>
              )}

              <Button
                onClick={() => setShowLogs((value) => !value)}

                size="small"
              >
                {tr(showLogs ? "Hide logs" : "Show logs")}
              </Button>
            </Stack>
          </Stack>

          <Collapse in={showLogs}>
            {logs.isPending && <LoadingState label={tr("Loading logs…")} />}

            {logs.isError && <FailureState error={logs.error} />}

            {logs.data &&
              (logs.data.available ? (
                <Box
                  component="pre"

                  sx={{
                    bgcolor: "grey.100",

                    maxHeight: 360,

                    overflow: "auto",

                    p: 2,

                    whiteSpace: "pre-wrap",
                  }}
                >
                  {tr(logs.data.content)}
                </Box>
              ) : (
                <Typography color="text.secondary">
                  {tr("No diagnostic log is available yet.")}
                </Typography>
              ))}
          </Collapse>
        </Stack>
      </Paper>

      {resource.status === "completed" && (
        <Stack direction={{ sm: "row", xs: "column" }} spacing={1}>
          {resource.results_url ? (
            <Button
              component={RouterLink}

              to={resource.results_url}

              variant="contained"
            >
              {tr("View results")}
            </Button>
          ) : (
            <Button disabled variant="contained">
              {tr("Results are being indexed")}
            </Button>
          )}

          <Button
            onClick={() => navigate(`/projects/${resource.scenario_id}`)}

            variant="outlined"
          >
            {tr("Return to scenario")}
          </Button>
        </Stack>
      )}
    </Stack>
  );
}

export function ProvisionalRunMap({ events }: { events: RunEvent[] }) {
  useLocale();

  const candidateNetwork: FeatureCollection = {
    type: "FeatureCollection",

    features: events.flatMap((event) => {
      if (event.event_type !== "optimization.candidate_completed") return [];

      const feature = event.data.provisional_geojson;

      if (!isLineFeature(feature)) return [];

      return [feature];
    }),
  };

  if (candidateNetwork.features.length === 0) return null;

  return (
    <Stack
      aria-labelledby="provisional-network-heading"

      component="section"

      spacing={1}
    >
      <Typography component="h2" id="provisional-network-heading" variant="h6">
        {tr("Provisional network")}
      </Typography>

      <Typography color="text.secondary" variant="body2">
        {tr(
          "Candidate decisions received so far. Final geometry is available after reporting completes.",
        )}
      </Typography>

      <ResultMap
        candidateNetwork={candidateNetwork}

        showCandidates

        showLhd={false}

        showPaths={false}

        title={tr("Provisional network map")}
      />
    </Stack>
  );
}

function isLineFeature(value: unknown): value is GeoJsonFeature {
  if (!value || typeof value !== "object") return false;

  const feature = value as Record<string, unknown>;

  const geometry = feature.geometry as Record<string, unknown> | null;

  return (
    feature.type === "Feature" &&
    geometry !== null &&
    typeof geometry === "object" &&
    geometry.type === "LineString" &&
    Array.isArray(geometry.coordinates)
  );
}

function useRunEventStream(
  runId: string | undefined,

  setEvents: (update: (current: RunEvent[]) => RunEvent[]) => void,
) {
  const lastSequence = useRef(0);

  useEffect(() => {
    if (!runId) return undefined;

    let disposed = false;

    let source: EventSource | null = null;

    const add = (event: RunEvent) => {
      if (
        event.sequence <= lastSequence.current &&
        event.event_type !== "heartbeat"
      )
        return;

      if (event.event_type !== "heartbeat")
        lastSequence.current = Math.max(lastSequence.current, event.sequence);

      setEvents((current) => {
        if (
          event.event_type !== "heartbeat" &&
          current.some((item) => item.sequence === event.sequence)
        )
          return current;

        return [...current, event].sort(
          (left, right) => left.sequence - right.sequence,
        );
      });
    };

    void getRunEvents(runId, 0)
      .then((initial) => {
        if (disposed) return;

        initial.forEach(add);

        source = new EventSource(runEventsUrl(runId, lastSequence.current));

        const onMessage = (message: MessageEvent<string>) => {
          try {
            add(JSON.parse(message.data) as RunEvent);
          } catch {
            // A malformed optional event must not take down the monitor.
          }
        };

        eventNames.forEach((name) => source?.addEventListener(name, onMessage));

        source.onerror = () => {
          // EventSource retries automatically; the polling query remains the
          // recovery path if a proxy closes the stream.
        };
      })

      .catch(() => {
        // Polling still restores the authoritative run state.
      });

    return () => {
      disposed = true;

      source?.close();
    };
  }, [runId, setEvents]);
}

function StageTimeline({
  current,

  status,
}: {
  current: string | null;

  status: string;
}) {
  useLocale();

  const stages = [
    "checking_input_data",

    "preparing_area",

    "finding_candidates",

    "optimizing_network",

    "load_inputs",

    "prepare_geospatial_data",

    "assess_heat_resources",

    "build_optimization_context",

    "optimize_heat_grid",

    "write_outputs",
  ];

  const currentIndex = stages.indexOf(current ?? "");

  return (
    <Stack direction={{ sm: "row", xs: "column" }} spacing={1}>
      {stages.map((stage, index) => (
        <Chip
          color={
            status === "failed" && index === currentIndex
              ? "error"
              : index < currentIndex || status === "completed"
                ? "success"
                : index === currentIndex
                  ? "primary"
                  : "default"
          }

          key={stage}

          label={tr(stageLabels[stage])}

          size="small"

          variant={index === currentIndex ? "filled" : "outlined"}
        />
      ))}
    </Stack>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  useLocale();

  return (
    <Box>
      <Typography color="text.secondary" variant="caption">
        {tr(label)}
      </Typography>

      <Typography fontWeight={600}>{tr(value)}</Typography>
    </Box>
  );
}

function plainLanguageEvent(event: RunEvent): string {
  const data = event.data;

  if (event.event_type === "pipeline.stage_started")
    return `Started ${stageLabels[String(data.stage)] ?? String(data.stage)}.`;

  if (event.event_type === "pipeline.stage_completed")
    return `Completed ${stageLabels[String(data.stage)] ?? String(data.stage)}.`;

  if (event.event_type === "optimization.candidate_started")
    return `Evaluating candidate ${String(data.candidate_id)}.`;

  if (event.event_type === "optimization.candidate_completed")
    return `Candidate ${String(data.candidate_id)} was ${String(data.decision)}.`;

  if (event.event_type === "job.failed")
    return `Run failed: ${String(data.message ?? "unknown error")}`;

  if (event.event_type === "job.status_changed")
    return `Run status changed to ${String(data.status)}.`;

  if (event.event_type === "artifact.created")
    return `Created artifact ${String(data.display_name ?? "output")}.`;

  if (event.event_type === "heartbeat") return "Worker heartbeat received.";

  return event.event_type;
}

function extractFailureIssues(
  details: Record<string, unknown>,
): Array<{ message: string; remediation?: string }> {
  if (!Array.isArray(details.issues)) return [];

  return details.issues.flatMap((value) => {
    if (!value || typeof value !== "object") return [];

    const issue = value as Record<string, unknown>;

    if (typeof issue.message !== "string") return [];

    return [
      {
        message: issue.message,

        remediation:
          typeof issue.remediation === "string" ? issue.remediation : undefined,
      },
    ];
  });
}

function statusColor(
  status: RunResource["status"],
): "default" | "success" | "warning" | "error" | "info" {
  if (status === "completed") return "success";

  if (status === "failed") return "error";

  if (status === "cancelled" || status === "cancellation_requested")
    return "warning";

  if (status === "running") return "info";

  return "default";
}
