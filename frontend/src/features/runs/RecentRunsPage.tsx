import { tr } from "../../i18n/translate";
import { useLocale, getFormatLocale } from "../../i18n/locale";
import {
  Button,
  Chip,
  List,
  ListItem,
  ListItemText,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { Link as RouterLink } from "react-router-dom";

import { useRecentRunsQuery } from "../../api/queries";
import type { RunStatus, RunSummary } from "../../api/workflow";
import {
  EmptyState,
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";
import {
  elapsedMs,
  formatDuration,
  isTerminalStatus,
  stageLabel,
} from "./runEvents";

/**
 * A recoverability list, deliberately not a project or comparison dashboard.
 *
 * It exists so a refresh, a closed browser, or a backgrounded tab cannot lose
 * a run link. It is never a step users have to pass through: `/` is the entry
 * point for starting work.
 */
export function RecentRunsPage() {
  useLocale();
  const runs = useRecentRunsQuery();

  if (runs.isPending)
    return <LoadingState label={tr("Loading recent runs…")} />;
  if (runs.isError) {
    return (
      <FailureState error={runs.error} onRetry={() => void runs.refetch()} />
    );
  }
  if (!runs.data?.items.length) {
    return (
      <EmptyState
        action={
          <Button component={RouterLink} to="/" variant="contained">
            {tr("Select a study area")}
          </Button>
        }
        body={tr(
          "Accepted calculations will stay here so a refresh or a closed browser does not lose the run link.",
        )}
        title={tr("No recent runs")}
      />
    );
  }

  return (
    <Stack spacing={2} sx={{ height: "100%", p: { sm: 3, xs: 1.5 } }}>
      <header>
        <Typography component="h1" variant="h4">
          {tr("Recent runs")}
        </Typography>
        <Typography color="text.secondary">
          {tr(
            "Reopen a calculation without passing through a project workspace.",
          )}
        </Typography>
      </header>
      <Paper
        component="section"
        elevation={0}
        sx={{ border: 1, borderColor: "divider" }}
      >
        <List aria-label={tr("Recent runs")}>
          {runs.data.items.map((run) => (
            <ListItem
              key={run.id}
              secondaryAction={
                <Button
                  component={RouterLink}
                  to={`/runs/${encodeURIComponent(run.id)}`}
                >
                  {tr("Open")}
                </Button>
              }
            >
              <ListItemText
                disableTypography
                primary={
                  <Stack
                    alignItems="center"
                    direction="row"
                    spacing={1}
                    sx={{ pr: 1 }}
                  >
                    <Typography fontWeight={600}>{run.name}</Typography>
                    <StatusChip status={run.status} />
                  </Stack>
                }
                secondary={<RunDescription now={Date.now()} run={run} />}
              />
            </ListItem>
          ))}
        </List>
      </Paper>
    </Stack>
  );
}

function StatusChip({ status }: { status: RunStatus }) {
  useLocale();
  const color =
    status === "completed"
      ? "success"
      : status === "failed"
        ? "error"
        : status === "cancelled" || status === "cancellation_requested"
          ? "warning"
          : "info";
  return (
    <Chip
      color={color}
      label={tr(
        status === "cancellation_requested" ? "cancellation requested" : status,
      )}
      size="small"
    />
  );
}

/** A finished run reports its duration; an unfinished one its current stage. */
function RunDescription({ run, now }: { run: RunSummary; now: number }) {
  useLocale();
  const updated = new Date(run.updated_at).toLocaleString(getFormatLocale());
  const duration = formatDuration(elapsedMs(run, now));
  const stage = run.stage ? stageLabel(run.stage) : null;
  return (
    <Typography color="text.secondary" variant="body2">
      {tr(
        isTerminalStatus(run.status)
          ? `${run.status} · ${duration} · updated ${updated}`
          : `${stage ?? "Queued"} · ${duration} elapsed · updated ${updated}`,
      )}
    </Typography>
  );
}
