import { tr } from "../../i18n/translate";

import { useLocale } from "../../i18n/locale";

import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Paper,
  Stack,
  Typography,
} from "@mui/material";

import { Link as RouterLink } from "react-router-dom";

import { resolveApiUrl } from "../../api/client";

import type { RunResource } from "../../api/workflow";

import {
  diagnosticCode,
  elapsedMs,
  extractFailureIssues,
  formatDuration,
  stageLabel,
} from "./runEvents";

export type RunFailureKind = "failed" | "cancelled" | "not-found";

export interface RunFailureProps {
  kind: RunFailureKind;

  /** The failed or stopped run. Omitted when the run is unknown entirely. */

  run?: RunResource;

  /**

   * Shown when no workspace header is present, so a requested identifier is

   * never lost on an error screen.

   */

  runId?: string;

  now?: number;
}

const headlines: Record<RunFailureKind, { title: string; body: string }> = {
  failed: {
    title: "This calculation did not finish",

    body: "The failure is recorded for this run. Nothing was changed in the stored configuration, and the selected study area is unchanged.",
  },

  cancelled: {
    title: "This calculation was cancelled",

    body: "The worker stopped before it produced results. The selected study area and the recorded configuration are unchanged.",
  },

  "not-found": {
    title: "This run could not be found",

    body: "The API has no run record for this address. Recent runs lists the calculations that are still available.",
  },
};

/**

 * A terminal state that is not a result.

 *

 * The failure stays inside the run workspace: the run identity, the stage it

 * stopped in, the elapsed time, and any actionable issues from the server stay

 * visible. Nothing is silently retried because a run is an immutable record.

 */

export function RunFailure({
  kind,

  run,

  runId,

  now = Date.now(),
}: RunFailureProps) {
  useLocale();

  const headline = headlines[kind];

  const issues = extractFailureIssues(run?.failure_details);

  const code = diagnosticCode(run?.failure_details);

  const elapsed = run ? elapsedMs(run, now) : null;

  const retryTarget = areaSelectionTarget(run);

  return (
    <Stack spacing={2}>
      <Alert severity={kind === "failed" ? "error" : "warning"}>
        <Typography fontWeight={600}>{tr(headline.title)}</Typography>

        <Typography variant="body2">{tr(headline.body)}</Typography>
      </Alert>

      {runId && !run && (
        <Typography color="text.secondary" variant="body2">
          {tr("Requested run: ")}

          {tr(runId)}
        </Typography>
      )}

      {run && (
        <Paper
          component="section"

          elevation={0}

          sx={{ border: 1, borderColor: "divider", p: 2 }}
        >
          <Stack spacing={1.5}>
            {run.failure_summary && (
              <Stack spacing={0.25}>
                <Typography component="h2" variant="subtitle2">
                  {tr("What happened")}
                </Typography>

                <Typography variant="body2">
                  {tr(run.failure_summary)}
                </Typography>
              </Stack>
            )}

            <Stack direction={{ sm: "row", xs: "column" }} spacing={2}>
              <Fact label={tr("Stage reached")} value={stageLabel(run.stage)} />

              <Fact
                label={tr("Time before stopping")}

                value={formatDuration(elapsed)}
              />
            </Stack>

            {issues.length > 0 && (
              <Box
                aria-label={tr("Reported issues")}

                component="ul"

                sx={{ mb: 0, pl: 2.5 }}
              >
                {issues.map((issue) => (
                  <li key={`${issue.message}:${issue.remediation ?? ""}`}>
                    <Typography variant="body2">
                      {tr(issue.message)}

                      {tr(issue.remediation ? ` ${issue.remediation}` : "")}
                    </Typography>
                  </li>
                ))}
              </Box>
            )}

            {run.bbox && (
              <Typography color="text.secondary" variant="body2">
                {tr("Study area kept for this run:")}

                {tr(" ")}

                {tr(run.bbox.map((value) => value.toFixed(6)).join(", "))}
              </Typography>
            )}
          </Stack>
        </Paper>
      )}

      <Stack
        alignItems={{ sm: "center", xs: "flex-start" }}

        direction={{ sm: "row", xs: "column" }}

        spacing={1}
      >
        <Button component={RouterLink} to={retryTarget} variant="contained">
          {tr(
            run
              ? "Start a new calculation with this area"
              : "Select a study area",
          )}
        </Button>

        <Button component={RouterLink} to="/recent" variant="outlined">
          {tr("Recent runs")}
        </Button>

        {run && (
          <Typography color="text.secondary" variant="body2">
            {tr("A new calculation always starts a new immutable run record.")}
          </Typography>
        )}
      </Stack>

      {(code || run?.log_url || run) && (
        <Accordion
          disableGutters

          elevation={0}

          sx={{
            backgroundColor: "transparent",

            "&:before": { display: "none" },
          }}
        >
          <AccordionSummary
            aria-controls="run-failure-diagnostics"

            expandIcon={<span aria-hidden="true">⌄</span>}

            id="run-failure-diagnostics-header"
          >
            <Typography fontWeight={600}>{tr("Technical details")}</Typography>
          </AccordionSummary>

          {/* The region MUI renders for `aria-controls` already carries this id. */}

          <AccordionDetails>
            <Stack spacing={1}>
              {code && (
                <Typography color="text.secondary" variant="body2">
                  {tr("Diagnostic code: ")}

                  {tr(code)}
                </Typography>
              )}

              {run?.application_version && (
                <Typography color="text.secondary" variant="body2">
                  {tr("Application version: ")}

                  {tr(run.application_version)}
                </Typography>
              )}

              {run?.configuration_version && (
                <Typography color="text.secondary" variant="body2">
                  {tr("Configuration version: ")}

                  {tr(run.configuration_version)}
                </Typography>
              )}

              {run?.log_url && (
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
            </Stack>
          </AccordionDetails>
        </Accordion>
      )}
    </Stack>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
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

/**

 * Carry the failed area back to the selection map.

 *

 * The run record is immutable, so "retry" means starting a new calculation for

 * the same rectangle instead of mutating this one. Only the rectangle is

 * handed back; the area page consumes it once.

 */

function areaSelectionTarget(run: RunResource | undefined): string {
  if (!run?.bbox) return "/";

  const query = new URLSearchParams({ bbox: run.bbox.join(",") });

  return `/?${query.toString()}`;
}
