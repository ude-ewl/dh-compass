import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { Button, Divider, Grid, Paper, Stack, Typography } from "@mui/material";
import {
  useResultCandidatesQuery,
  useResultCostsQuery,
  useResultNetworkQuery,
  useResultSummaryQuery,
  useResultSupplyQuery,
} from "../../api/queries";
import type { CostResult, SupplyResult } from "../../api/results";
import {
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";
import { AccessibleBarChart } from "./AccessibleBarChart";
import { ResultUnavailable, ResultWarnings } from "./ResultFeedback";
import { CandidateInspector, CandidateTable } from "./CandidateTable";
import { formatEuro, formatMwh, formatNumber } from "./format";
import { KpiCards } from "./KpiCards";
import { ResultMap } from "./ResultMap";
import { useResultSelection } from "./selection";

export function OverviewPage({ runId }: { runId: string }) {
  useLocale();
  const summary = useResultSummaryQuery(runId);
  const network = useResultNetworkQuery(runId, [
    "final_network",
    "candidate_network",
    "connection_paths",
  ]);
  const candidates = useResultCandidatesQuery(runId);
  const supply = useResultSupplyQuery(runId);
  const costs = useResultCostsQuery(runId);
  const { candidateId: selectedCandidateId, selectCandidate } =
    useResultSelection();

  if (summary.isPending || network.isPending || candidates.isPending) {
    return <LoadingState label={tr("Loading result overview…")} />;
  }
  if (summary.isError)
    return (
      <FailureState
        error={summary.error}
        onRetry={() => void summary.refetch()}
      />
    );
  if (network.isError)
    return (
      <FailureState
        error={network.error}
        onRetry={() => void network.refetch()}
      />
    );
  if (candidates.isError)
    return (
      <FailureState
        error={candidates.error}
        onRetry={() => void candidates.refetch()}
      />
    );
  if (!summary.data?.available || !summary.data.data) {
    return <ResultUnavailable warnings={summary.data?.warnings} />;
  }

  const summaryData = summary.data.data;
  const networkData = network.data?.available ? network.data.data : null;
  const candidateData =
    candidates.data?.available && candidates.data.data
      ? candidates.data.data
      : [];
  const selectedCandidate =
    candidateData.find((candidate) => candidate.id === selectedCandidateId) ??
    null;
  const totalCost = numberValue(summaryData.total_annualized_eur);
  const connectedDemand = numberValue(summaryData.connected_heat_demand_mwh);
  const costPerConnectedMwh =
    totalCost !== undefined && connectedDemand && connectedDemand > 0
      ? totalCost / connectedDemand
      : undefined;

  return (
    <Stack className="printable-results" spacing={3}>
      <Stack
        alignItems={{ sm: "center", xs: "flex-start" }}
        direction={{ sm: "row", xs: "column" }}
        justifyContent="space-between"
        spacing={1}
      >
        <Typography component="h2" variant="h5">
          {tr("Results overview")}
        </Typography>
        <Button onClick={() => window.print()} variant="outlined">
          {tr("Print result overview")}
        </Button>
      </Stack>
      <KpiCards
        connectedBuildings={numberValue(summaryData.connected_buildings)}
        costPerConnectedMwh={costPerConnectedMwh}
        networkLength={numberValue(summaryData.total_network_length_m)}
        peakLoad={numberValue(summaryData.peak_load_kw)}
        runId={runId}
        summary={summaryData}
        totalCost={totalCost}
      />
      <ResultWarnings
        warnings={[
          ...(summary.data.warnings ?? []),
          ...(network.data?.warnings ?? []),
          ...(candidates.data?.warnings ?? []),
        ]}
      />
      <Grid container spacing={2}>
        <Grid item md={8} xs={12}>
          <ResultMap
            candidateNetwork={networkData?.candidate_network}
            connectionPaths={networkData?.connection_paths}
            finalNetwork={networkData?.final_network}
            lhd={networkData?.lhd}
            onSelectCandidate={selectCandidate}
            screenedOut={networkData?.screened_out}
            selectedCandidateId={selectedCandidateId}
            showBuildings={Boolean(networkData?.buildings)}
            title={tr("Final network and candidate areas")}
          />
        </Grid>
        <Grid item md={4} xs={12}>
          <CandidateInspector candidate={selectedCandidate} />
        </Grid>
      </Grid>
      {candidateData.length > 0 ? (
        <CandidateTable
          candidates={candidateData}
          onSelect={selectCandidate}
          selectedCandidateId={selectedCandidateId}
        />
      ) : (
        <ResultUnavailable
          body={tr("Candidate records are not available for this output.")}
          title={tr("Candidate details unavailable")}
        />
      )}
      <Grid container spacing={2}>
        <Grid item md={6} xs={12}>
          <DemandSummary summary={summaryData} />
        </Grid>
        <Grid item md={6} xs={12}>
          <PortfolioSummary
            result={supply.data?.available ? supply.data.data : null}
            query={supply}
          />
        </Grid>
        <Grid item md={6} xs={12}>
          <CostSummary
            result={costs.data?.available ? costs.data.data : null}
            query={costs}
          />
        </Grid>
      </Grid>
    </Stack>
  );
}

function DemandSummary({ summary }: { summary: Record<string, unknown> }) {
  useLocale();
  const chart = [
    {
      label: "Connected",
      value: numberValue(summary.connected_heat_demand_mwh),
    },
    {
      label: "Disconnected",
      value: numberValue(summary.disconnected_heat_demand_mwh),
    },
  ];
  return (
    <Stack spacing={2}>
      <Paper
        component="section"
        elevation={0}
        sx={{ border: 1, borderColor: "divider", p: 2 }}
      >
        <Typography component="h2" gutterBottom variant="h6">
          {tr("Connected demand")}
        </Typography>
        <Stack spacing={1}>
          <Metric
            label={tr("Total demand")}
            value={formatMwh(summary.total_heat_demand_mwh)}
          />
          <Metric
            label={tr("Connected demand")}
            value={formatMwh(summary.connected_heat_demand_mwh)}
          />
          <Metric
            label={tr("Disconnected demand")}
            value={formatMwh(summary.disconnected_heat_demand_mwh)}
          />
          <Metric
            label={tr("Connected share")}
            value={`${formatNumber(summary.connected_share_pct, 1)}%`}
          />
        </Stack>
      </Paper>
      <AccessibleBarChart
        data={chart}
        formatValue={(value) => formatMwh(value)}
        title={tr("Connected versus disconnected demand")}
        valueLabel="Demand (MWh/a)"
      />
    </Stack>
  );
}

function PortfolioSummary({
  result,
  query,
}: {
  result: SupplyResult | null | undefined;
  query: { isPending: boolean; isError: boolean; error: unknown };
}) {
  useLocale();
  if (query.isPending) return <LoadingState label={tr("Loading supply…")} />;
  if (query.isError) return <FailureState error={query.error} />;
  if (!result)
    return <ResultUnavailable title={tr("Supply data unavailable")} />;
  const technologies = Object.entries(result.supply ?? {});
  return (
    <Stack spacing={2}>
      <Paper
        component="section"
        elevation={0}
        sx={{ border: 1, borderColor: "divider", p: 2 }}
      >
        <Typography component="h2" gutterBottom variant="h6">
          {tr("Supply portfolio")}
        </Typography>
        {technologies.length === 0 ? (
          <Typography color="text.secondary">
            {tr("No supply technologies were reported.")}
          </Typography>
        ) : (
          <Stack divider={<Divider flexItem />} spacing={1}>
            {technologies.map(([name, technology]) => (
              <Metric
                key={name}
                label={tr(name.replaceAll("_", " "))}
                value={formatMwh(
                  technology.annual_energy_mwh ??
                    technology.annual_heat_energy_mwh,
                )}
              />
            ))}
          </Stack>
        )}
        <Typography color="text.secondary" sx={{ mt: 1 }} variant="body2">
          {tr("Total heat production: ")}
          {tr(formatMwh(result.total_heat_production_mwh))}
        </Typography>
      </Paper>
      <AccessibleBarChart
        data={technologies.map(([name, technology]) => ({
          label: name.replaceAll("_", " "),
          value:
            technology.annual_energy_mwh ?? technology.annual_heat_energy_mwh,
        }))}
        formatValue={(value) => formatMwh(value)}
        title={tr("Annual heat production by technology")}
        valueLabel="Heat (MWh/a)"
      />
    </Stack>
  );
}

function CostSummary({
  result,
  query,
}: {
  result: CostResult | null | undefined;
  query: { isPending: boolean; isError: boolean; error: unknown };
}) {
  useLocale();
  if (query.isPending) return <LoadingState label={tr("Loading costs…")} />;
  if (query.isError) return <FailureState error={query.error} />;
  if (!result) return <ResultUnavailable title={tr("Cost data unavailable")} />;
  return (
    <Stack spacing={2}>
      <Paper
        component="section"
        elevation={0}
        sx={{ border: 1, borderColor: "divider", p: 2 }}
      >
        <Typography component="h2" gutterBottom variant="h6">
          {tr("Grid and supply cost split")}
        </Typography>
        <Stack spacing={1}>
          <Metric
            label={tr("Total annualized")}
            value={formatEuro(result.total_annualized_eur)}
          />
          <Metric
            label={tr("Supply")}
            value={formatEuro(result.supply_annualized_eur)}
          />
          <Metric
            label={tr("Grid")}
            value={formatEuro(result.grid_annualized_eur)}
          />
          <Metric
            label={tr("Supply share")}
            value={`${formatNumber(result.supply_share_pct, 1)}%`}
          />
        </Stack>
      </Paper>
      <AccessibleBarChart
        data={[
          { label: "Supply", value: result.supply_annualized_eur },
          { label: "Grid", value: result.grid_annualized_eur },
        ]}
        formatValue={(value) => formatEuro(value)}
        title={tr("Annualized grid versus supply costs")}
        valueLabel="Cost (€/a)"
      />
    </Stack>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  useLocale();
  return (
    <Stack direction="row" justifyContent="space-between" spacing={2}>
      <Typography color="text.secondary" variant="body2">
        {tr(label)}
      </Typography>
      <Typography fontWeight={600} variant="body2">
        {tr(value)}
      </Typography>
    </Stack>
  );
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : undefined;
}
