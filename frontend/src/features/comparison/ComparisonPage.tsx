import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
  Alert,
  Button,
  Checkbox,
  FormControlLabel,
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
import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  Link as RouterLink,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";

import { createComparison } from "../../api/client";
import type {
  ComparisonMetricRow,
  ComparisonResource,
} from "../../api/comparison";
import { useComparisonQuery, useRunsQuery } from "../../api/queries";
import {
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";
import { t } from "../../i18n/messages";
import { formatDate, formatEuro, formatNumber } from "../results/format";
import { ResultMap } from "../results/ResultMap";

export function ComparisonPage() {
  useLocale();
  const { comparisonId } = useParams();
  const [searchParams] = useSearchParams();
  const [runPage, setRunPage] = useState(1);
  const runs = useRunsQuery(runPage);
  const initialIds = useMemo(
    () =>
      (searchParams.get("runs") ?? "")
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean),
    [searchParams],
  );
  const [selectedIds, setSelectedIds] = useState<string[]>(initialIds);
  const comparison = useComparisonQuery(comparisonId);
  const navigate = useNavigate();
  const create = useMutation({
    mutationFn: (runIds: string[]) => createComparison(runIds),
    onSuccess: (result) =>
      navigate(`/compare/${encodeURIComponent(result.id)}`),
  });

  useEffect(() => {
    if (!comparisonId && initialIds.length > 0) setSelectedIds(initialIds);
  }, [comparisonId, initialIds]);

  if (comparisonId) {
    if (comparison.isPending)
      return <LoadingState label={t("loadingComparison")} />;
    if (comparison.isError)
      return (
        <FailureState
          error={comparison.error}
          onRetry={() => void comparison.refetch()}
        />
      );
    if (!comparison.data)
      return (
        <FailureState error={new Error("The comparison is unavailable.")} />
      );
    return <ComparisonResult comparison={comparison.data} />;
  }

  if (runs.isPending)
    return <LoadingState label={t("loadingRunsForComparison")} />;
  if (runs.isError)
    return (
      <FailureState error={runs.error} onRetry={() => void runs.refetch()} />
    );

  const completedRuns =
    runs.data?.items.filter((run) => run.status === "completed") ?? [];
  return (
    <Stack spacing={3}>
      <header>
        <Typography component="h1" variant="h4">
          {t("compareRuns")}
        </Typography>
        <Typography color="text.secondary">{t("compareRunsIntro")}</Typography>
      </header>
      <Paper
        component="section"
        elevation={0}
        sx={{ border: 1, borderColor: "divider", p: 2 }}
      >
        <Stack spacing={1}>
          {completedRuns.length === 0 ? (
            <Typography color="text.secondary">
              {t("noCompletedRunsForComparison")}
            </Typography>
          ) : (
            completedRuns.map((run) => {
              const checked = selectedIds.includes(run.id);
              return (
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={checked}
                      inputProps={{
                        "aria-label": `Select ${run.display_name}`,
                      }}
                      onChange={() =>
                        setSelectedIds((current) =>
                          checked
                            ? current.filter((id) => id !== run.id)
                            : current.length < 4
                              ? [...current, run.id]
                              : current,
                        )
                      }
                    />
                  }
                  key={run.id}
                  label={
                    <span>
                      {run.display_name}
                      {tr(" ")}
                      <small>({tr(formatDate(run.updated_at))})</small>
                    </span>
                  }
                />
              );
            })
          )}
          <Stack
            alignItems="center"
            direction="row"
            justifyContent="space-between"
          >
            <Typography color="text.secondary" variant="body2">
              {t("comparisonSelectionCount", { count: selectedIds.length })}
            </Typography>
            <Stack direction="row" spacing={1}>
              <Button
                disabled={!runs.data?.pagination.has_previous}
                onClick={() => setRunPage((page) => Math.max(1, page - 1))}
              >
                {tr("Previous")}
              </Button>
              <Button
                disabled={!runs.data?.pagination.has_next}
                onClick={() => setRunPage((page) => page + 1)}
              >
                {tr("Next")}
              </Button>
            </Stack>
          </Stack>
          {create.isError && (
            <Alert severity="error">{tr(create.error.message)}</Alert>
          )}
          <Stack direction="row" spacing={1}>
            <Button
              disabled={selectedIds.length < 2 || create.isPending}
              onClick={() => create.mutate(selectedIds)}
              variant="contained"
            >
              {tr(
                create.isPending
                  ? t("creatingComparison")
                  : t("compareSelected"),
              )}
            </Button>
            <Button component={RouterLink} to="/runs">
              {t("backToResults")}
            </Button>
          </Stack>
        </Stack>
      </Paper>
    </Stack>
  );
}

function ComparisonResult({ comparison }: { comparison: ComparisonResource }) {
  useLocale();
  return (
    <Stack spacing={3}>
      <header>
        <Typography component="h1" variant="h4">
          {t("comparisonWorkspace")}
        </Typography>
        <Typography color="text.secondary">
          {tr(comparison.runs.map((run) => run.label).join(" · "))}
        </Typography>
      </header>
      <CompatibilityBanner comparison={comparison} />
      <ComparisonTable
        columns={comparison.runs.map((run) => ({
          id: run.id,
          label: run.label,
        }))}
        rows={comparison.kpi_differences}
        title={t("kpiDifferences")}
        valueFormatter={(value) => formatNumber(value, 1)}
      />
      <ConfigurationChanges comparison={comparison} />
      <ComparisonTable
        columns={comparison.runs.map((run) => ({
          id: run.id,
          label: run.label,
        }))}
        rows={comparison.supply}
        title={t("supplyComparison")}
        valueFormatter={(value) => formatNumber(value, 1)}
        rowLabel={(row) => row.technology ?? "—"}
      />
      <ComparisonTable
        columns={comparison.runs.map((run) => ({
          id: run.id,
          label: run.label,
        }))}
        rows={comparison.costs}
        title={t("costComparison")}
        valueFormatter={(value) => formatEuro(value)}
      />
      <NetworkComparison comparison={comparison} />
      <MuiLink component={RouterLink} to="/runs">
        {t("backToResults")}
      </MuiLink>
    </Stack>
  );
}

function CompatibilityBanner({
  comparison,
}: {
  comparison: ComparisonResource;
}) {
  useLocale();
  const unknown = comparison.compatibility.filter(
    (item) => item.status === "unknown",
  );
  const different = comparison.compatibility.filter(
    (item) => item.status === "different",
  );
  return (
    <Alert
      severity={
        different.length > 0
          ? "warning"
          : unknown.length > 0
            ? "info"
            : "success"
      }
    >
      <Typography fontWeight={600}>{t("comparisonCompatibility")}</Typography>
      <ul>
        {comparison.compatibility.map((item) => (
          <li key={item.key}>{tr(item.message)}</li>
        ))}
      </ul>
    </Alert>
  );
}

function ComparisonTable({
  columns,
  rows,
  title,
  valueFormatter,
  rowLabel,
}: {
  columns: Array<{ id: string; label: string }>;
  rows: ComparisonMetricRow[];
  title: string;
  valueFormatter: (value: unknown) => string;
  rowLabel?: (row: ComparisonMetricRow) => string;
}) {
  useLocale();
  return (
    <Paper
      component="section"
      elevation={0}
      sx={{ border: 1, borderColor: "divider", overflowX: "auto" }}
    >
      <Typography component="h2" sx={{ p: 2 }} variant="h6">
        {tr(title)}
      </Typography>
      {rows.length === 0 ? (
        <Typography color="text.secondary" sx={{ px: 2, pb: 2 }}>
          {t("noComparisonValues")}
        </Typography>
      ) : (
        <Table aria-label={tr(title)} size="small">
          <TableHead>
            <TableRow>
              <TableCell>{tr("Metric")}</TableCell>
              {columns.map((column) => (
                <TableCell key={column.id} align="right">
                  {tr(column.label)}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.key ?? row.technology}>
                <TableCell>{tr(rowLabel?.(row) ?? row.key ?? "—")}</TableCell>
                {columns.map((column) => (
                  <TableCell key={column.id} align="right">
                    <div>{tr(valueFormatter(row.values[column.id]))}</div>
                    <Typography color="text.secondary" variant="caption">
                      Δ{tr(" ")}
                      {tr(
                        row.deltas[column.id] == null
                          ? "—"
                          : valueFormatter(row.deltas[column.id]),
                      )}
                    </Typography>
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Paper>
  );
}

function ConfigurationChanges({
  comparison,
}: {
  comparison: ComparisonResource;
}) {
  useLocale();
  return (
    <Paper
      component="section"
      elevation={0}
      sx={{ border: 1, borderColor: "divider", overflowX: "auto" }}
    >
      <Typography component="h2" sx={{ p: 2 }} variant="h6">
        {t("configurationChanges")}
      </Typography>
      {comparison.configuration_changes.length === 0 ? (
        <Typography color="text.secondary" sx={{ px: 2, pb: 2 }}>
          {t("noConfigurationChanges")}
        </Typography>
      ) : (
        <Table aria-label={t("configurationChanges")} size="small">
          <TableHead>
            <TableRow>
              <TableCell>{tr("Setting")}</TableCell>
              <TableCell>{tr("Scope")}</TableCell>
              {comparison.runs.map((run) => (
                <TableCell key={run.id}>{tr(run.label)}</TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {comparison.configuration_changes.map((change) => (
              <TableRow key={change.path}>
                <TableCell>{tr(change.path)}</TableCell>
                <TableCell>
                  {tr(change.setting_type === "expert" ? "Expert" : "Standard")}
                </TableCell>
                {comparison.runs.map((run) => (
                  <TableCell key={run.id}>
                    {tr(displayValue(change.values[run.id]))}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Paper>
  );
}

function NetworkComparison({ comparison }: { comparison: ComparisonResource }) {
  useLocale();
  return (
    <Paper
      component="section"
      elevation={0}
      sx={{ border: 1, borderColor: "divider", p: 2 }}
    >
      <Typography component="h2" variant="h6">
        {t("networkComparison")}
      </Typography>
      <Typography color="text.secondary" variant="body2">
        {t("networkComparisonHint")}
      </Typography>
      <Stack direction={{ lg: "row", xs: "column" }} spacing={2} sx={{ mt: 2 }}>
        {comparison.network.runs.map((run) => (
          <Stack key={run.run_id} spacing={1} sx={{ flex: 1, minWidth: 0 }}>
            <Typography fontWeight={600}>{run.run_id}</Typography>
            <Typography color="text.secondary" variant="body2">
              {tr(
                run.available ? t("networkAvailable") : t("networkUnavailable"),
              )}
              {tr(" ")}· {tr(run.feature_count)} {tr(" features")}
            </Typography>
            <ResultMap
              finalNetwork={run.final_network}
              showBuildings={false}
              showCandidates={false}
              showLhd={false}
              showPaths={false}
              title={tr(`${t("networkComparison")} — ${run.run_id}`)}
            />
          </Stack>
        ))}
      </Stack>
    </Paper>
  );
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
