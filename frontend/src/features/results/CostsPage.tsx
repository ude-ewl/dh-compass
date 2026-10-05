import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
  Grid,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

import { useResultCostsQuery } from "../../api/queries";
import {
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";
import { AccessibleBarChart } from "./AccessibleBarChart";
import { CostReconciliationNotice } from "./CostReconciliation";
import { ResultUnavailable, ResultWarnings } from "./ResultFeedback";
import { formatEuro, formatEuroCapital } from "./format";

export function CostsPage({ runId }: { runId: string }) {
  useLocale();
  const costs = useResultCostsQuery(runId);
  if (costs.isPending)
    return <LoadingState label={tr("Loading cost breakdown…")} />;
  if (costs.isError)
    return (
      <FailureState error={costs.error} onRetry={() => void costs.refetch()} />
    );
  if (!costs.data?.available || !costs.data.data) {
    return (
      <ResultUnavailable
        warnings={costs.data?.warnings}
        title={tr("Cost breakdown unavailable")}
      />
    );
  }
  const result = costs.data.data;
  const supplyBreakdown = flattenNumbers(result.supply_breakdown);
  const gridBreakdown = flattenNumbers(result.grid_breakdown);

  return (
    <Stack spacing={2}>
      <Typography component="h2" variant="h5">
        {tr("Costs")}
      </Typography>
      <ResultWarnings warnings={costs.data.warnings} />
      <Grid container spacing={2}>
        <Grid item md={4} sm={6} xs={12}>
          <CostCard
            label={tr("Total annualized")}
            value={result.total_annualized_eur}
          />
        </Grid>
        <Grid item md={4} sm={6} xs={12}>
          <CostCard label={tr("Supply")} value={result.supply_annualized_eur} />
        </Grid>
        <Grid item md={4} sm={6} xs={12}>
          <CostCard label={tr("Grid")} value={result.grid_annualized_eur} />
        </Grid>
      </Grid>
      <CostReconciliationNotice
        grid={result.grid_annualized_eur}
        supply={result.supply_annualized_eur}
        total={result.total_annualized_eur}
      />
      <AccessibleBarChart
        data={[
          { label: "Supply", value: result.supply_annualized_eur },
          { label: "Grid", value: result.grid_annualized_eur },
        ]}
        formatValue={(value) => formatEuro(value)}
        title={tr("Annualized cost split")}
        valueLabel="Cost (€/a)"
      />
      <Grid container spacing={2}>
        <Grid item md={6} xs={12}>
          <Breakdown
            title={tr("Supply breakdown")}
            rows={supplyBreakdown}
            value={result.supply_breakdown}
          />
        </Grid>
        <Grid item md={6} xs={12}>
          <Breakdown
            title={tr("Grid infrastructure breakdown")}
            rows={gridBreakdown}
            value={result.grid_breakdown}
            formatValue={formatGridBreakdownValue}
          />
        </Grid>
      </Grid>
      {result.by_technology && (
        <Breakdown
          title={tr("Cost by technology")}
          rows={flattenNumbers(result.by_technology)}
          value={result.by_technology}
        />
      )}
      {result.by_candidate && (
        <Breakdown
          title={tr("Cost by candidate")}
          rows={flattenNumbers(result.by_candidate)}
          value={result.by_candidate}
        />
      )}
    </Stack>
  );
}

function CostCard({ label, value }: { label: string; value?: number }) {
  useLocale();
  return (
    <Paper elevation={0} sx={{ border: 1, borderColor: "divider", p: 2 }}>
      <Typography color="text.secondary" variant="overline">
        {tr(label)}
      </Typography>
      <Typography variant="h5">{tr(formatEuro(value))}</Typography>
      <Typography color="text.secondary" variant="body2">
        {tr(
          "Annualized values; raw investment values are labelled separately.",
        )}
      </Typography>
    </Paper>
  );
}

function Breakdown({
  title,
  value,
  rows,
  formatValue = (_label, item) => formatEuro(item),
}: {
  title: string;
  value?: Record<string, unknown>;
  rows: [string, number][];
  formatValue?: (label: string, value: number) => string;
}) {
  useLocale();
  if (!value) return <ResultUnavailable title={tr(`${title} unavailable`)} />;
  return (
    <Paper
      component="section"
      elevation={0}
      sx={{ border: 1, borderColor: "divider", overflowX: "auto" }}
    >
      <Typography component="h2" sx={{ p: 2, pb: 1 }} variant="h6">
        {tr(title)}
      </Typography>
      <Table aria-label={tr(title)} size="small">
        <TableHead>
          <TableRow>
            <TableCell>{tr("Category")}</TableCell>
            <TableCell align="right">{tr("Value (unit shown)")}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map(([label, value]) => (
            <TableRow key={label}>
              <TableCell>{tr(label)}</TableCell>
              <TableCell align="right">
                {tr(formatValue(label, value))}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {!rows.length && (
        <Typography color="text.secondary" sx={{ p: 2 }}>
          {tr("No numeric breakdown was reported.")}
        </Typography>
      )}
    </Paper>
  );
}

function formatGridBreakdownValue(label: string, value: number): string {
  return label.endsWith("raw total eur")
    ? formatEuroCapital(value)
    : formatEuro(value);
}

function flattenNumbers(
  value: Record<string, unknown> | undefined,
  prefix = "",
): [string, number][] {
  if (!value) return [];
  const rows: [string, number][] = [];
  Object.entries(value).forEach(([key, item]) => {
    const label = prefix
      ? `${prefix} / ${key.replaceAll("_", " ")}`
      : key.replaceAll("_", " ");
    if (typeof item === "number" && Number.isFinite(item))
      rows.push([label, item]);
    else if (item && typeof item === "object" && !Array.isArray(item)) {
      rows.push(...flattenNumbers(item as Record<string, unknown>, label));
    }
  });
  return rows;
}
