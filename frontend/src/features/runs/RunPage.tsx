import { tr } from "../../i18n/translate";

import { useLocale } from "../../i18n/locale";

import { Typography } from "@mui/material";

import { useMemo } from "react";

import { useParams } from "react-router-dom";

import { isApiClientError } from "../../api/client";

import { useManagedRunQuery } from "../../api/queries";

import type { RunResource, RunStatus } from "../../api/workflow";

import {
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";

import { ResultSummary } from "../results/ResultSummary";

import { bboxAreaKm2, formatAreaKm2, formatCoordinate } from "../area/bbox";

import { RunFailure, type RunFailureKind } from "./RunFailure";

import { RunProgress } from "./RunProgress";

import {
  elapsedMs,
  formatDuration,
  isTerminalStatus,
  stageLabel,
  workerState,
} from "./runEvents";

import { useNow } from "./useNow";

import { useRunEvents } from "./useRunEvents";

import { GridViewer } from "../viewer/GridViewer";

import { CompletedGridViewer } from "../viewer/CompletedGridViewer";

import { liveGrid } from "../viewer/viewerState";

/**

 * One route for the whole lifecycle of a calculation.

 *

 * The workspace renders according to the authoritative run state: progress

 * while work is queued or running, a terminal explanation for failure or

 * cancellation, and the result summary once reporting finished. There is no

 * separate monitor or results URL to navigate to, and the run identity stays

 * on screen in every state.

 */

export function RunPage() {
  useLocale();

  const { runId } = useParams();

  const run = useManagedRunQuery(runId);

  if (!runId) {
    return <FailureState error={new Error("The run identifier is missing.")} />;
  }

  if (run.isPending) {
    return <LoadingState label={tr("Restoring run workspace…")} />;
  }

  if (run.isSuccess && run.data) {
    return (
      <ManagedRunWorkspace
        onRefresh={() => void run.refetch()}

        run={run.data}
      />
    );
  }

  if (isRunNotFound(run.error)) {
    // The requested identifier stays on screen so it can be compared with the

    // run list; the address itself is unchanged and can simply be reloaded.

    return <RunFailure kind="not-found" now={Date.now()} runId={runId} />;
  }

  return (
    <FailureState
      error={run.error ?? new Error("The run is unavailable.")}

      onRetry={() => void run.refetch()}
    />
  );
}

function ManagedRunWorkspace({
  run,

  onRefresh,
}: {
  run: RunResource;

  onRefresh: () => void;
}) {
  useLocale();

  const terminal = isTerminalStatus(run.status);

  const now = useNow(!terminal);

  const worker = workerState(run, now);

  const elapsed = elapsedMs(run, now);

  const { events, streamState } = useRunEvents(
    run.id,

    run.status !== "completed",

    !terminal,
  );

  const grid = useMemo(() => liveGrid(events), [events]);

  if (run.status === "completed") {
    return (
      <CompletedGridViewer
        key={run.id}

        runId={run.id}

        title={tr(run.name)}

        subtitle={tr(
          `Completed · Run ${run.id} · ${formatDuration(elapsed)} elapsed`,
        )}

        bbox={run.bbox}
      />
    );
  }

  return (
    <GridViewer
      key={run.id}

      steps={grid.steps}

      network={grid.network}

      lhd={grid.network}

      live={!terminal}

      bbox={run.bbox}

      title={tr(run.name)}

      subtitle={tr(
        `${statusLabel(run.status)} · ${stageLabel(run.stage)} · Run ${run.id} · ${formatDuration(elapsed)} elapsed`,
      )}
    >
      {run.bbox && (
        <Typography variant="caption" color="text.secondary">
          {tr("Study area · ")}
          {tr(formatAreaKm2(bboxAreaKm2(run.bbox)))} ·{tr(" ")}
          {tr(run.bbox.map(formatCoordinate).join(", "))}
        </Typography>
      )}

      {worker && (
        <Typography
          color={worker.tone === "warning" ? "warning.main" : "text.secondary"}

          variant="body2"
        >
          {tr(worker.label)}
        </Typography>
      )}

      {terminal ? (
        <TerminalRunView now={now} run={run} />
      ) : (
        <RunProgress
          showMap={false}

          events={events}

          onRefresh={onRefresh}

          run={run}

          streamState={streamState}
        />
      )}
    </GridViewer>
  );
}

/** Completion, failure, and cancellation each get one honest explanation. */

function TerminalRunView({ run, now }: { run: RunResource; now: number }) {
  useLocale();

  if (run.status === "completed") return <ResultSummary runId={run.id} />;

  const kind: RunFailureKind =
    run.status === "cancelled" ? "cancelled" : "failed";

  return <RunFailure kind={kind} now={now} run={run} />;
}

function statusLabel(status: RunStatus): string {
  if (status === "cancellation_requested") return "Cancellation requested";

  if (status === "queued") return "Queued";

  return status.charAt(0).toUpperCase() + status.slice(1);
}

function isRunNotFound(error: unknown): boolean {
  return isApiClientError(error) && error.status === 404;
}
