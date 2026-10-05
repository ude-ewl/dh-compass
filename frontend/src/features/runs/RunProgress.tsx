import { tr } from "../../i18n/translate";

import { useLocale, getFormatLocale } from "../../i18n/locale";

import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from "@mui/material";

import { useMutation, useQuery } from "@tanstack/react-query";

import { useState } from "react";

import { Link as RouterLink } from "react-router-dom";

import { cancelRun, getRunLogs, resolveApiUrl } from "../../api/client";

import type { RunEvent, RunResource } from "../../api/workflow";

import {
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";

import { PanelErrorBoundary } from "../../components/feedback/PanelErrorBoundary";

import { ResultMap } from "../results/ResultMap";

import {
  RUN_STAGES,
  canCancel,
  describeEvent,
  measuredFraction,
  provisionalNetwork,
  stageLabel,
  stageStates,
  warningMessages,
} from "./runEvents";

import type { RunStreamState } from "./useRunEvents";

export interface RunProgressProps {
  showMap?: boolean;

  run: RunResource;

  events: RunEvent[];

  streamState: RunStreamState;

  /** Re-read the authoritative run resource, e.g. after a cancellation. */

  onRefresh: () => void;
}

/**

 * The running part of the unified run workspace.

 *

 * Every value shown here is reported by the server: the current stage, a

 * measured fraction when one exists, worker heartbeats, and streamed events.

 * Live updates are an enhancement over polling, so an interrupted stream or a

 * rejected cancellation request stays inside this panel.

 */

export function RunProgress({
  showMap = true,

  run,

  events,

  streamState,

  onRefresh,
}: RunProgressProps) {
  useLocale();

  const [confirmCancel, setConfirmCancel] = useState(false);

  const cancel = useMutation({
    mutationFn: () => cancelRun(run.id),

    onSuccess: () => {
      setConfirmCancel(false);

      onRefresh();
    },
  });

  const fraction = measuredFraction(run);

  const states = stageStates(run.stage, run.status);

  const network = provisionalNetwork(events);

  const warnings = warningMessages(run);

  const cancelling = run.status === "cancellation_requested";

  const cancellable = canCancel(run.status);

  const progress = run.candidate_progress;

  return (
    <Stack spacing={2}>
      {warnings.length > 0 && (
        <Alert severity="warning">
          <Typography fontWeight={600} variant="body2">
            {tr("Warnings from this run")}
          </Typography>

          <Box component="ul" sx={{ mb: 0, mt: 0.5, pl: 2 }}>
            {warnings.map((warning) => (
              <li key={warning}>
                <Typography variant="body2">{tr(warning)}</Typography>
              </li>
            ))}
          </Box>
        </Alert>
      )}

      {streamState === "interrupted" && (
        <Alert severity="info">
          {tr(
            "Live updates are interrupted. The stage and elapsed time keep being read from the run record while the connection recovers.",
          )}
        </Alert>
      )}

      {cancelling && (
        <Alert severity="info">
          {tr(
            "Cancellation was requested. The worker finishes its current safe operation before the run reports Cancelled.",
          )}
        </Alert>
      )}

      {cancel.isError && (
        <FailureState
          error={cancel.error}

          onRetry={() => {
            void cancel.mutate();
          }}
        />
      )}

      <Paper
        aria-label={tr("Run progress details")}

        component="section"

        elevation={0}

        sx={{ border: 1, borderColor: "divider", p: 2 }}
      >
        <Stack spacing={2}>
          <Stack spacing={0.5}>
            <Typography component="h2" variant="h6">
              {tr(stageLabel(run.stage))}
            </Typography>

            <Typography
              aria-live="polite"

              color="text.secondary"

              variant="body2"
            >
              {tr(
                run.status === "queued"
                  ? "Queued. The calculation starts as soon as a worker is available."
                  : "Reporting the stage the calculation actually reached.",
              )}
            </Typography>
          </Stack>

          <LinearProgress
            aria-label={tr("Run progress")}

            value={fraction === null ? undefined : fraction * 100}

            variant={fraction === null ? "indeterminate" : "determinate"}
          />

          <Typography color="text.secondary" variant="body2">
            {tr(
              fraction === null
                ? "The backend cannot quantify this stage, so no percentage is shown."
                : `${Math.round(fraction * 100)}% reported by the worker`,
            )}
          </Typography>

          <Stack
            aria-label={tr("Run stages")}

            direction="row"

            flexWrap="wrap"

            spacing={1}

            useFlexGap

            sx={{ minWidth: 0, "& > .MuiChip-root": { maxWidth: "100%" } }}
          >
            {RUN_STAGES.map((stage, index) => (
              <Chip
                aria-current={states[index] === "current" ? "step" : undefined}

                color={
                  states[index] === "current"
                    ? "primary"
                    : states[index] === "done"
                      ? "success"
                      : "default"
                }

                key={stage.id}

                label={tr(stage.label)}

                size="small"

                variant={states[index] === "current" ? "filled" : "outlined"}
              />
            ))}
          </Stack>

          {progress && (
            <Stack
              divider={<Divider flexItem />}

              direction={{ sm: "row", xs: "column" }}

              spacing={2}
            >
              <Metric
                label={tr("Candidates evaluated")}

                value={`${progress.completed_candidates} / ${
                  progress.total_candidates ?? "—"
                }`}
              />

              <Metric
                label={tr("Connected")}

                value={String(progress.connected_candidates)}
              />

              <Metric
                label={tr("Rejected")}

                value={String(progress.rejected_candidates)}
              />
            </Stack>
          )}
        </Stack>
      </Paper>

      {cancellable && (
        <Paper
          component="section"

          elevation={0}

          sx={{ border: 1, borderColor: "divider", p: 1.5 }}
        >
          <Stack
            alignItems={{ sm: "center", xs: "flex-start" }}

            direction={{ sm: "row", xs: "column" }}

            justifyContent="space-between"

            spacing={1}
          >
            <Typography color="text.secondary" variant="body2">
              {tr(
                "The calculation keeps running if you leave this page or open another run.",
              )}
            </Typography>

            <Stack direction="row" spacing={1}>
              <Button
                component={RouterLink}

                size="small"

                to="/recent"

                variant="text"
              >
                {tr("Recent runs")}
              </Button>

              {!confirmCancel ? (
                <Button
                  color="warning"

                  disabled={cancel.isPending}

                  onClick={() => setConfirmCancel(true)}

                  variant="outlined"
                >
                  {tr("Cancel run")}
                </Button>
              ) : (
                <>
                  <Button
                    color="warning"

                    disabled={cancel.isPending}

                    onClick={() => cancel.mutate()}

                    variant="contained"
                  >
                    {tr(
                      cancel.isPending ? "Requesting…" : "Confirm cancellation",
                    )}
                  </Button>

                  <Button
                    disabled={cancel.isPending}

                    onClick={() => setConfirmCancel(false)}

                    variant="text"
                  >
                    {tr("Keep running")}
                  </Button>
                </>
              )}
            </Stack>
          </Stack>
        </Paper>
      )}

      {showMap && network.features.length > 0 && (
        <Stack spacing={1}>
          <Typography component="h2" variant="h6">
            {tr("Provisional network")}
          </Typography>

          <Typography color="text.secondary" variant="body2">
            {tr(
              "Candidate decisions reported so far. This is intermediate information, not the final result.",
            )}
          </Typography>

          <PanelErrorBoundary
            resetKey={`${run.id}:provisional:${events.length}`}

            title={tr("Provisional network map")}
          >
            <ResultMap
              candidateNetwork={network}

              showCandidates

              showLhd={false}

              showPaths={false}

              title={tr("Provisional network map")}
            />
          </PanelErrorBoundary>
        </Stack>
      )}

      <RunActivity events={events} run={run} />
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

      <Typography fontWeight={600} variant="body2">
        {tr(value)}
      </Typography>
    </Box>
  );
}

/** Activity and diagnostics stay collapsed until they are actually needed. */

function RunActivity({
  events,

  run,
}: {
  events: RunEvent[];

  run: RunResource;
}) {
  useLocale();

  const [expanded, setExpanded] = useState(false);

  const logs = useQuery({
    queryKey: ["managed-run", run.id, "logs"],

    queryFn: () => getRunLogs(run.id),

    enabled: expanded,

    retry: false,
  });

  return (
    <Accordion
      disableGutters

      elevation={0}

      sx={{ backgroundColor: "transparent", "&:before": { display: "none" } }}
    >
      <AccordionSummary
        aria-controls="run-activity-content"

        expandIcon={<span aria-hidden="true">⌄</span>}

        id="run-activity-header"

        onClick={() => setExpanded((value) => !value)}
      >
        <Stack>
          <Typography fontWeight={600}>
            {tr("Activity and diagnostics")}
          </Typography>

          <Typography color="text.secondary" variant="caption">
            {tr(events.length)} {tr(" event")}
            {tr(events.length === 1 ? "" : "s")}
            {tr(", worker logs, and request identifiers.")}
          </Typography>
        </Stack>
      </AccordionSummary>

      {/* The region MUI renders for `aria-controls` already carries this id. */}

      <AccordionDetails>
        <Stack spacing={2}>
          <Stack spacing={0.5}>
            <Typography component="h3" variant="subtitle2">
              {tr("Worker")}
            </Typography>

            <Typography color="text.secondary" variant="body2">
              {tr(workerDescription(run))}
            </Typography>
          </Stack>

          <Stack spacing={0.5}>
            <Typography component="h3" variant="subtitle2">
              {tr("Events")}
            </Typography>

            {events.length === 0 ? (
              <Typography color="text.secondary" variant="body2">
                {tr(
                  "No events have arrived yet. Status polling remains authoritative.",
                )}
              </Typography>
            ) : (
              <Stack divider={<Divider flexItem />} spacing={0.5}>
                {events.slice(-40).map((event) => (
                  <Stack
                    direction={{ sm: "row", xs: "column" }}

                    key={`${event.sequence}-${event.id}`}

                    spacing={1}
                  >
                    <Typography
                      color="text.secondary"

                      sx={{ minWidth: 56 }}

                      variant="caption"
                    >
                      #{tr(event.sequence)}
                    </Typography>

                    <Typography variant="body2">
                      {tr(describeEvent(event))}
                    </Typography>
                  </Stack>
                ))}
              </Stack>
            )}
          </Stack>

          <Stack spacing={0.5}>
            <Typography component="h3" variant="subtitle2">
              {tr("Worker log")}
            </Typography>

            {run.log_url && (
              <Button
                component="a"

                href={resolveApiUrl(run.log_url)}

                size="small"

                sx={{ alignSelf: "flex-start" }}

                target="_blank"

                variant="outlined"
              >
                {tr("Download diagnostics")}
              </Button>
            )}

            {logs.isPending && <LoadingState label={tr("Loading logs…")} />}

            {logs.isError && <FailureState error={logs.error} />}

            {logs.data &&
              (logs.data.available ? (
                <Box
                  component="pre"

                  sx={{
                    bgcolor: "grey.100",

                    maxHeight: 320,

                    overflow: "auto",

                    p: 2,

                    whiteSpace: "pre-wrap",
                  }}
                >
                  {tr(logs.data.content)}
                </Box>
              ) : (
                <Typography color="text.secondary" variant="body2">
                  {tr("No diagnostic log is available yet.")}
                </Typography>
              ))}
          </Stack>
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}

function workerDescription(run: RunResource): string {
  const identity = run.process_identity;

  if (!identity?.pid) {
    return run.status === "queued"
      ? "No worker process is attached yet."
      : "No worker process is attached to this run.";
  }

  const heartbeat = identity.heartbeat_at
    ? new Date(identity.heartbeat_at).toLocaleString(getFormatLocale())
    : "not reported yet";

  return `Process ${identity.pid} · last heartbeat ${heartbeat}.`;
}
