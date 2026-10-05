import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { Chip, Paper, Stack, Typography } from "@mui/material";

import type { CandidateRecord } from "../../api/results";
import {
  formatMetricValue,
  MetricDefinitionsDisclosure,
} from "./MetricDisplay";

export function CandidateInspector({
  candidate,
}: {
  candidate: CandidateRecord | null;
}) {
  useLocale();
  if (!candidate) {
    return (
      <Paper
        component="aside"
        elevation={0}
        sx={{ border: 1, borderColor: "divider", p: 2 }}
      >
        <Typography color="text.secondary">
          {tr(
            "Select a candidate on the map or in the table to inspect its decision.",
          )}
        </Typography>
      </Paper>
    );
  }

  const margin = decisionMargin(candidate);
  const metrics = [
    "candidate.annual_heat_demand_mwh",
    "candidate.buildings",
    "candidate.peak_load_kw",
    "candidate.total_network_length_m",
    "candidate.connection_length_m",
    "candidate.average_lhd",
    "candidate.central_cost",
    "candidate.decentral_cost",
    "candidate.central_grid_cost_raw",
    "candidate.decision_margin",
    "candidate.decision_step",
    "candidate.cost_breakdown_investment",
    "candidate.cost_breakdown_fixed_om",
    "candidate.cost_breakdown_operational",
    "candidate.technology_annual_energy_mwh",
    "candidate.storage_capacity_kwh",
    "candidate.storage_power_kw",
    "candidate.total_heat_production_mwh",
  ] as const;

  return (
    <Paper
      component="aside"
      elevation={0}
      sx={{ border: 1, borderColor: "divider", p: 2 }}
    >
      <Stack spacing={1}>
        <Stack
          alignItems="center"
          direction="row"
          justifyContent="space-between"
        >
          <Typography component="h2" variant="h6">
            {tr("Candidate #")}
            {tr(candidate.id)}
          </Typography>
          <Chip
            color={candidate.decision === "connected" ? "success" : "error"}
            label={tr(candidate.decision)}
            size="small"
          />
        </Stack>
        <Typography color="text.secondary" variant="caption">
          {tr("Optimization recorded this area as ")}
          {tr(candidate.decision)}
          {tr(
            ". The values below are candidate-local evidence, not final-system totals.",
          )}
        </Typography>
        <MetricDefinitionsDisclosure metrics={[...metrics]} />
        <Detail
          label={tr("Annual demand")}
          value={formatMetricValue(
            "candidate.annual_heat_demand_mwh",
            candidate.annual_heat_demand_mwh,
          )}
        />
        <Detail
          label={tr("Buildings")}
          value={formatMetricValue("candidate.buildings", candidate.buildings)}
        />
        <Detail
          label={tr("Peak load")}
          value={formatMetricValue(
            "candidate.peak_load_kw",
            candidatePeakLoadKw(candidate),
          )}
        />
        <Detail
          label={tr("Trial network length")}
          value={formatMetricValue(
            "candidate.total_network_length_m",
            candidate.total_network_length_m,
          )}
        />
        <Detail
          label={tr("Connection length")}
          value={formatMetricValue(
            "candidate.connection_length_m",
            candidate.connection_length_m,
          )}
        />
        <Detail
          label={tr("Average LHD")}
          value={formatMetricValue(
            "candidate.average_lhd",
            candidate.average_linear_heat_density_mwh_per_m_a ??
              candidate.avg_lhd,
          )}
        />
        <Detail
          label={tr("Central cost")}
          value={formatMetricValue(
            "candidate.central_cost",
            candidate.central_cost,
          )}
        />
        <Detail
          label={tr("Decentralized cost")}
          value={formatMetricValue(
            "candidate.decentral_cost",
            candidate.decentral_cost,
          )}
        />
        <Detail
          label={tr("Grid investment (raw capital)")}
          value={formatMetricValue(
            "candidate.central_grid_cost_raw",
            candidate.central_grid_cost_raw,
          )}
        />
        <Detail
          label={tr("Decision margin (decentralized − central)")}
          value={formatMetricValue("candidate.decision_margin", margin)}
        />
        <CandidateCostBreakdown value={candidate.cost_breakdown} />
        <CandidatePortfolio candidate={candidate} />
        {typeof candidate.iteration_step === "number" && (
          <Detail
            label={tr("Decision step")}
            value={formatMetricValue(
              "candidate.decision_step",
              candidate.iteration_step + 1,
            )}
          />
        )}
      </Stack>
    </Paper>
  );
}

function candidatePeakLoadKw(candidate: CandidateRecord): number | undefined {
  if (typeof candidate.peak_load_kw === "number") return candidate.peak_load_kw;
  return typeof candidate.peak_load_mw === "number"
    ? candidate.peak_load_mw * 1_000
    : undefined;
}

function decisionMargin(candidate: CandidateRecord): number | undefined {
  if (typeof candidate.decision_margin_eur === "number") {
    return candidate.decision_margin_eur;
  }
  if (typeof candidate.difference_eur === "number") {
    return candidate.difference_eur;
  }
  if (
    typeof candidate.decentral_cost !== "number" ||
    typeof candidate.central_cost !== "number"
  ) {
    return undefined;
  }
  return candidate.decentral_cost - candidate.central_cost;
}

function CandidateCostBreakdown({
  value,
}: {
  value: Record<string, unknown> | undefined;
}) {
  useLocale();
  if (!value) return null;
  const investment = nestedNumber(value, "investment", "total_eur");
  const fixedOm = nestedNumber(value, "fixed_om", "total_eur");
  const operational = nestedNumber(
    value,
    "operational",
    "net_operational_annual_eur",
  );
  if (
    investment === undefined &&
    fixedOm === undefined &&
    operational === undefined
  )
    return null;
  return (
    <>
      <Typography component="h3" sx={{ pt: 1 }} variant="subtitle2">
        {tr("Central cost breakdown")}
      </Typography>
      <Detail
        label={tr("Investment component")}
        value={formatMetricValue(
          "candidate.cost_breakdown_investment",
          investment,
        )}
      />
      <Detail
        label={tr("Fixed O&M component")}
        value={formatMetricValue("candidate.cost_breakdown_fixed_om", fixedOm)}
      />
      <Detail
        label={tr("Operational component")}
        value={formatMetricValue(
          "candidate.cost_breakdown_operational",
          operational,
        )}
      />
    </>
  );
}

function CandidatePortfolio({ candidate }: { candidate: CandidateRecord }) {
  useLocale();
  const technologies = Object.entries(candidate.supply ?? {});
  const storage = Object.entries(candidate.storage ?? {});
  if (!technologies.length && !storage.length) return null;
  return (
    <>
      <Typography component="h3" sx={{ pt: 1 }} variant="subtitle2">
        {tr("Candidate supply and storage")}
      </Typography>
      {technologies.map(([name, technology]) => (
        <Detail
          key={`technology-${name}`}
          label={tr(name.replaceAll("_", " "))}
          value={formatMetricValue(
            "candidate.technology_annual_energy_mwh",
            technology.annual_energy_mwh ?? technology.annual_heat_energy_mwh,
          )}
        />
      ))}
      {storage.map(([name, item]) => (
        <Stack key={`storage-${name}`} spacing={0.25}>
          <Detail
            label={tr(`${name.replaceAll("_", " ")} capacity`)}
            value={formatMetricValue(
              "candidate.storage_capacity_kwh",
              item.capacity_kwh,
            )}
          />
          <Detail
            label={tr(`${name.replaceAll("_", " ")} power`)}
            value={formatMetricValue(
              "candidate.storage_power_kw",
              item.power_kw,
            )}
          />
        </Stack>
      ))}
      <Detail
        label={tr("Total heat production")}
        value={formatMetricValue(
          "candidate.total_heat_production_mwh",
          candidate.total_heat_production_mwh,
        )}
      />
    </>
  );
}

function nestedNumber(
  value: Record<string, unknown>,
  section: string,
  key: string,
): number | undefined {
  const nested = value[section];
  if (!nested || typeof nested !== "object") return undefined;
  const item = (nested as Record<string, unknown>)[key];
  return typeof item === "number" && Number.isFinite(item) ? item : undefined;
}

function Detail({ label, value }: { label: string; value: string }) {
  useLocale();
  return (
    <Stack direction="row" justifyContent="space-between" spacing={2}>
      <Typography color="text.secondary" variant="body2">
        {tr(label)}
      </Typography>
      <Typography
        fontWeight={600}
        sx={{ fontVariantNumeric: "tabular-nums", textAlign: "right" }}
        variant="body2"
      >
        {tr(value)}
      </Typography>
    </Stack>
  );
}
