import { tr } from "../../i18n/translate";

import { useLocale } from "../../i18n/locale";

import {
  Button,
  Checkbox,
  Chip,
  Link as MuiLink,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

import { useState } from "react";

import { Link as RouterLink, useNavigate } from "react-router-dom";

import { useRunsQuery } from "../../api/queries";

import {
  EmptyState,
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";

import type { RunManifest } from "../../api/results";

import { formatDate, formatEuro, formatMwh, formatNumber } from "./format";

export function ResultsPortalPage() {
  useLocale();

  const navigate = useNavigate();

  const [page, setPage] = useState(1);

  const runs = useRunsQuery(page);

  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  if (runs.isPending)
    return <LoadingState label={tr("Discovering output runs…")} />;

  if (runs.isError)
    return (
      <FailureState error={runs.error} onRetry={() => void runs.refetch()} />
    );

  if (!runs.data?.items.length) {
    return (
      <EmptyState
        action={
          <Button component={RouterLink} to="/" variant="contained">
            {tr("Return to workspace")}
          </Button>
        }

        body={tr(
          "Run DH-COMPASS from the command line, then open this page to inspect its output artifacts.",
        )}

        title={tr("No completed runs discovered")}
      />
    );
  }

  return (
    <Stack spacing={3}>
      <header>
        <Typography component="h1" variant="h4">
          {tr("Results portal")}
        </Typography>

        <Typography color="text.secondary">
          {tr(
            "Inspect existing DH-COMPASS output folders without regenerating a run.",
          )}
        </Typography>
      </header>

      <Stack
        alignItems={{ sm: "center", xs: "flex-start" }}

        direction={{ sm: "row", xs: "column" }}

        justifyContent="space-between"

        spacing={1}
      >
        <Typography color="text.secondary" variant="body2">
          {tr(
            "Select two to four completed runs to compare their assumptions and outcomes.",
          )}
        </Typography>

        <Button
          disabled={selectedIds.length < 2}

          onClick={() =>
            navigate(
              `/compare?runs=${selectedIds.map(encodeURIComponent).join(",")}`,
            )
          }

          variant="contained"
        >
          {tr("Compare selected (")}
          {tr(selectedIds.length)})
        </Button>
      </Stack>

      <Paper
        component="section"

        elevation={0}

        sx={{ border: 1, borderColor: "divider", overflowX: "auto" }}
      >
        <Table aria-label={tr("Discovered DH-COMPASS runs")}>
          <TableHead>
            <TableRow>
              <TableCell>{tr("Select")}</TableCell>

              <TableCell>{tr("Run")}</TableCell>

              <TableCell>{tr("Status")}</TableCell>

              <TableCell align="right">{tr("Connected demand")}</TableCell>

              <TableCell align="right">{tr("Connected share")}</TableCell>

              <TableCell align="right">{tr("Cost")}</TableCell>

              <TableCell>{tr("Updated")}</TableCell>

              <TableCell align="right">{tr("Action")}</TableCell>
            </TableRow>
          </TableHead>

          <TableBody>
            {runs.data.items.map((run) => (
              <RunRow
                key={run.id}

                onToggle={() =>
                  setSelectedIds((current) =>
                    current.includes(run.id)
                      ? current.filter((id) => id !== run.id)
                      : current.length < 4
                        ? [...current, run.id]
                        : current,
                  )
                }

                run={run}

                selected={selectedIds.includes(run.id)}
              />
            ))}
          </TableBody>
        </Table>
      </Paper>

      <RunPagination
        page={runs.data.pagination.page}

        pageSize={runs.data.pagination.page_size}

        total={runs.data.pagination.total}

        hasNext={runs.data.pagination.has_next}

        hasPrevious={runs.data.pagination.has_previous}

        onPageChange={setPage}
      />
    </Stack>
  );
}

function RunPagination({
  page,

  pageSize,

  total,

  hasNext,

  hasPrevious,

  onPageChange,
}: {
  page: number;

  pageSize: number;

  total: number;

  hasNext: boolean;

  hasPrevious: boolean;

  onPageChange: (page: number) => void;
}) {
  useLocale();

  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;

  const last = Math.min(page * pageSize, total);

  return (
    <Stack alignItems="center" direction="row" justifyContent="space-between">
      <Typography color="text.secondary" variant="body2">
        {tr("Showing ")}
        {tr(first)}–{tr(last)} {tr(" of ")}
        {tr(total)} {tr(" runs.")}
      </Typography>

      <Stack direction="row" spacing={1}>
        <Button disabled={!hasPrevious} onClick={() => onPageChange(page - 1)}>
          {tr("Previous")}
        </Button>

        <Button disabled={!hasNext} onClick={() => onPageChange(page + 1)}>
          {tr("Next")}
        </Button>
      </Stack>
    </Stack>
  );
}

function RunRow({
  run,

  selected,

  onToggle,
}: {
  run: RunManifest;

  selected: boolean;

  onToggle: () => void;
}) {
  useLocale();

  const summary = run.summary ?? {};

  return (
    <TableRow hover>
      <TableCell>
        <Checkbox
          aria-label={tr(`Select ${run.display_name}`)}

          checked={selected}

          disabled={run.status !== "completed"}

          onChange={onToggle}
        />
      </TableCell>

      <TableCell>
        <MuiLink
          component={RouterLink}

          fontWeight={600}

          to={`/runs/${encodeURIComponent(run.id)}/results/overview`}
        >
          {run.display_name}
        </MuiLink>

        <Typography color="text.secondary" variant="caption">
          {tr(run.scenario)}
        </Typography>
      </TableCell>

      <TableCell>
        <Chip
          color={run.status === "completed" ? "success" : "warning"}

          label={tr(run.status)}

          size="small"
        />
      </TableCell>

      <TableCell align="right">
        {tr(formatMwh(summary.connected_heat_demand_mwh))}
      </TableCell>

      <TableCell align="right">
        {tr(formatNumber(summary.connected_share_pct, 1))}%
      </TableCell>

      <TableCell align="right">
        {tr(formatEuro(summary.total_annualized_eur))}
      </TableCell>

      <TableCell>{tr(formatDate(run.updated_at))}</TableCell>

      <TableCell align="right">
        <Button
          component={RouterLink}

          size="small"

          to={`/runs/${encodeURIComponent(run.id)}/results/overview`}
        >
          {tr("Open")}
        </Button>
      </TableCell>
    </TableRow>
  );
}
