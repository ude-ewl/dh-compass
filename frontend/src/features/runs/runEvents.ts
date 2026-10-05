import type { FeatureCollection, GeoJsonFeature } from "../../api/results";
import type { RunEvent, RunResource, RunStatus } from "../../api/workflow";

/**
 * Pure run-lifecycle helpers for the unified run workspace.
 *
 * The workspace has to stay honest about what the backend knows: a stage name,
 * a measured fraction, worker heartbeats, and events. Nothing here invents a
 * percentage, and everything is separated from the SSE plumbing so keyboard,
 * refresh, and recovery behavior can be characterized without a live stream.
 */

/** Canonical stages in the order a calculation actually advances. */
export const RUN_STAGES = [
  { id: "checking_input_data", label: "Checking input data" },
  { id: "preparing_area", label: "Preparing area" },
  { id: "finding_candidates", label: "Finding candidates" },
  { id: "optimizing_network", label: "Optimizing network" },
  { id: "preparing_results", label: "Preparing results" },
  { id: "complete", label: "Complete" },
] as const;

export type CanonicalStage = (typeof RUN_STAGES)[number]["id"];

export type StageState = "done" | "current" | "pending";

/**
 * Backend stage keys mapped to the user-facing vocabulary.
 *
 * The calculation job folds data validation, preprocessing, candidate
 * generation, and optimization into one lifecycle, while the older run worker
 * reported its pipeline stages separately. Both map onto the same six steps so
 * a run keeps one understandable progression.
 */
const STAGE_ALIASES: Record<
  string,
  { label: string; canonical: CanonicalStage }
> = {
  starting: { label: "Queued", canonical: "checking_input_data" },
  load_inputs: {
    label: "Checking input data",
    canonical: "checking_input_data",
  },
  checking_input_data: {
    label: "Checking input data",
    canonical: "checking_input_data",
  },
  validate_datasets: {
    label: "Checking input data",
    canonical: "checking_input_data",
  },
  prepare_geospatial_data: {
    label: "Preparing area",
    canonical: "preparing_area",
  },
  preparing_area: { label: "Preparing area", canonical: "preparing_area" },
  build_preview: { label: "Preparing area", canonical: "preparing_area" },
  assess_heat_resources: {
    label: "Finding candidates",
    canonical: "finding_candidates",
  },
  find_candidates: {
    label: "Finding candidates",
    canonical: "finding_candidates",
  },
  finding_candidates: {
    label: "Finding candidates",
    canonical: "finding_candidates",
  },
  build_optimization_context: {
    label: "Optimizing network",
    canonical: "optimizing_network",
  },
  optimize_heat_grid: {
    label: "Optimizing network",
    canonical: "optimizing_network",
  },
  optimizing_network: {
    label: "Optimizing network",
    canonical: "optimizing_network",
  },
  write_outputs: { label: "Preparing results", canonical: "preparing_results" },
  preparing_results: {
    label: "Preparing results",
    canonical: "preparing_results",
  },
  complete: { label: "Complete", canonical: "complete" },
};

const UNKNOWN_STAGE_LABEL = "Working";

export function stageLabel(stage: string | null | undefined): string {
  if (!stage) return "Queued";
  return STAGE_ALIASES[stage]?.label ?? humanizeStage(stage);
}

/** The canonical step a backend stage belongs to, or `null` when unknown. */
export function canonicalStage(
  stage: string | null | undefined,
): CanonicalStage | null {
  if (!stage) return null;
  return STAGE_ALIASES[stage]?.canonical ?? null;
}

function humanizeStage(stage: string): string {
  const text = stage.replaceAll("_", " ").trim();
  if (!text) return UNKNOWN_STAGE_LABEL;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * Ordered stage states for the current position.
 *
 * Steps before the current one are only marked as done once the run has
 * actually reported a later stage, so an unmeasured future step is never shown
 * as finished.
 */
export function stageStates(
  stage: string | null | undefined,
  status: RunStatus,
): StageState[] {
  if (status === "completed") return RUN_STAGES.map(() => "done");
  const current = canonicalStage(stage);
  const currentIndex = RUN_STAGES.findIndex((item) => item.id === current);
  return RUN_STAGES.map((_, index) => {
    if (currentIndex < 0) return "pending";
    if (index < currentIndex) return "done";
    if (index === currentIndex) return "current";
    return "pending";
  });
}

export function isTerminalStatus(status: RunStatus): boolean {
  return (
    status === "completed" || status === "failed" || status === "cancelled"
  );
}

/** The timing fields shared by the run resource and the recovery list. */
export type RunTimeline = Pick<
  RunResource,
  "status" | "started_at" | "finished_at" | "created_at" | "updated_at"
>;

export function canCancel(status: RunStatus): boolean {
  return status === "queued" || status === "running";
}

/** A measured fraction, or `null` when the backend cannot quantify progress. */
export function measuredFraction(run: RunResource): number | null {
  const fraction = run.progress?.fraction;
  if (typeof fraction !== "number" || !Number.isFinite(fraction)) return null;
  return Math.min(1, Math.max(0, fraction));
}

function timestampMs(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

/**
 * Elapsed wall-clock time for a run.
 *
 * A queued run counts from creation, a started run from `started_at`, and a
 * finished run stops at `finished_at` so the value never keeps growing after
 * the job is done.
 */
export function elapsedMs(run: RunTimeline, now: number): number | null {
  if (isTerminalStatus(run.status)) {
    const start = timestampMs(run.started_at) ?? timestampMs(run.created_at);
    const end = timestampMs(run.finished_at) ?? timestampMs(run.updated_at);
    if (start === null) return null;
    return Math.max(0, (end ?? start) - start);
  }
  const start = timestampMs(run.started_at) ?? timestampMs(run.created_at);
  if (start === null) return null;
  return Math.max(0, now - start);
}

/** Compact, locale-independent duration such as `4 m 07 s` or `1 h 04 m`. */
export function formatDuration(milliseconds: number | null): string {
  if (milliseconds === null || !Number.isFinite(milliseconds)) return "—";
  const total = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours > 0) return `${hours} h ${pad(minutes)} m`;
  if (minutes > 0) return `${minutes} m ${pad(seconds)} s`;
  return `${seconds} s`;
}

function pad(value: number): string {
  return value.toString().padStart(2, "0");
}

export type WorkerTone = "neutral" | "active" | "warning";

export interface WorkerState {
  label: string;
  tone: WorkerTone;
  heartbeatAt: string | null;
}

/** A heartbeat older than this is reported as delayed, not as a failure. */
export const HEARTBEAT_DELAY_MS = 60_000;

/**
 * Describe the worker attached to a run.
 *
 * "Queued" and "running without a worker" are genuinely different situations,
 * and a stalled heartbeat must not be reported as healthy work.
 */
export function workerState(run: RunResource, now: number): WorkerState | null {
  if (isTerminalStatus(run.status)) return null;
  const identity = run.process_identity;
  const heartbeatAt = identity?.heartbeat_at ?? null;
  const heartbeat = timestampMs(heartbeatAt);

  if (run.status === "queued") {
    return {
      label: identity?.pid
        ? "Starting worker"
        : "Queued — waiting for a worker",
      tone: identity?.pid ? "active" : "neutral",
      heartbeatAt,
    };
  }
  if (run.status === "cancellation_requested") {
    return {
      label: "Cancellation requested — finishing the current safe operation",
      tone: "warning",
      heartbeatAt,
    };
  }
  if (!identity?.pid) {
    return {
      label: "Running without an attached worker process",
      tone: "warning",
      heartbeatAt,
    };
  }
  if (heartbeat === null) {
    return { label: "Worker running", tone: "active", heartbeatAt };
  }
  if (now - heartbeat > HEARTBEAT_DELAY_MS) {
    return {
      label: "Worker heartbeat is delayed",
      tone: "warning",
      heartbeatAt,
    };
  }
  return { label: "Worker running", tone: "active", heartbeatAt };
}

/**
 * Event names the run stream emits.
 *
 * The stream uses named SSE frames, so the browser only delivers an event to a
 * listener registered for its exact name. Both lifecycle implementations are
 * therefore listed: the calculation job reports `calculation.stage_*`, and the
 * optimization worker reports `pipeline.stage_*` and `optimization.candidate_*`.
 * `runEventNames` additionally subscribes to anything already observed, so a new
 * backend event type is never silently dropped from the activity feed.
 */
export const RUN_EVENT_NAMES = [
  "job.status_changed",
  "calculation.stage_started",
  "calculation.stage_completed",
  "pipeline.stage_started",
  "pipeline.stage_completed",
  "optimization.candidate_started",
  "optimization.candidate_completed",
  "artifact.created",
  "job.warning",
  "job.failed",
  "heartbeat",
] as const;

/**
 * Every event name worth subscribing to, including names seen in replay.
 *
 * A named SSE frame for an unsubscribed type is discarded by the browser, so
 * the observed names widen the subscription instead of relying on this list
 * staying complete.
 */
export function runEventNames(observed: RunEvent[] = []): string[] {
  const names = new Set<string>(RUN_EVENT_NAMES);
  for (const event of observed) names.add(event.event_type);
  return [...names];
}

/**
 * Merge replayed and streamed events into one ordered, duplicate-free list.
 *
 * Heartbeats carry the current sequence instead of a new one, so they are only
 * used as connection evidence and never enter the visible activity feed.
 */
export function mergeRunEvents(
  current: RunEvent[],
  incoming: RunEvent[],
): RunEvent[] {
  if (incoming.length === 0) return current;
  const seen = new Set(current.map((event) => event.sequence));
  const merged = [...current];
  for (const event of incoming) {
    if (event.event_type === "heartbeat") continue;
    if (seen.has(event.sequence)) continue;
    seen.add(event.sequence);
    merged.push(event);
  }
  if (merged.length === current.length) return current;
  return merged.sort((left, right) => left.sequence - right.sequence);
}

export function describeEvent(event: RunEvent): string {
  const data = event.data;
  switch (event.event_type) {
    case "calculation.stage_started":
    case "pipeline.stage_started":
      return `Started ${stageLabel(stringValue(data.stage)).toLowerCase()}.`;
    case "calculation.stage_completed":
    case "pipeline.stage_completed":
      return `Completed ${stageLabel(stringValue(data.stage)).toLowerCase()}.`;
    case "optimization.candidate_started":
      return `Evaluating candidate ${stringValue(data.candidate_id)}.`;
    case "optimization.candidate_completed":
      return `Candidate ${stringValue(data.candidate_id)} was ${stringValue(data.decision)}.`;
    case "job.status_changed":
      return `Run status changed to ${stringValue(data.status)}.`;
    case "job.warning":
      return `Warning: ${stringValue(data.message ?? data.code)}.`;
    case "job.failed":
      return `Run failed: ${stringValue(data.message ?? data.code)}.`;
    case "artifact.created":
      return `Created artifact ${stringValue(data.display_name)}.`;
    default:
      // An unmodelled event still belongs in a sentence a reader can follow;
      // the raw identifier never reaches the activity feed.
      return `${humanizeEventType(event.event_type)}.`;
  }
}

function humanizeEventType(eventType: string): string {
  const text = eventType
    .replaceAll(/[._]/g, " ")
    .replaceAll(/\s+/g, " ")
    .trim();
  if (!text) return UNKNOWN_STAGE_LABEL;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function stringValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

export interface FailureIssue {
  message: string;
  remediation?: string;
}

/** Read actionable issues out of a failure envelope without inventing any. */
export function extractFailureIssues(
  details: Record<string, unknown> | null | undefined,
): FailureIssue[] {
  if (!details || !Array.isArray(details.issues)) return [];
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

export function diagnosticCode(
  details: Record<string, unknown> | null | undefined,
): string | null {
  const code = details?.code;
  return typeof code === "string" && code ? code : null;
}

export function isLineFeature(value: unknown): value is GeoJsonFeature {
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

/**
 * Candidate geometry observed so far.
 *
 * Final geometry is only available after reporting; showing these lines is
 * explicitly labelled as provisional so they cannot be read as the result.
 */
export function provisionalNetwork(events: RunEvent[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: events.flatMap((event) => {
      if (event.event_type !== "optimization.candidate_completed") return [];
      const feature = event.data.provisional_geojson;
      return isLineFeature(feature) ? [feature] : [];
    }),
  };
}

export function warningMessages(run: Pick<RunResource, "warnings">): string[] {
  return run.warnings
    .filter((warning) => warning.severity !== "info")
    .map((warning) =>
      warning.remediation
        ? `${warning.message} ${warning.remediation}`
        : warning.message,
    );
}
