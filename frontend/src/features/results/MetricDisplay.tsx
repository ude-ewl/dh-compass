import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { Box, Stack, Typography } from "@mui/material";
import { useState } from "react";

import type { ResultMetricId } from "./metricContract";
import { metricDefinition } from "./metricContract";
import {
  formatEuro,
  formatEuroCapital,
  formatEuroPerMwh,
  formatMwh,
  formatNumber,
} from "./format";

/**
 * Render a result value using the unit declared by the metric contract.
 *
 * Formatting is deliberately kept next to the contract lookup. A value that
 * is moved from a candidate table to the final summary therefore has to name
 * a different metric instead of silently reusing a formatter with a different
 * scope or cost basis.
 */
export function formatMetricValue(
  metric: ResultMetricId,
  value: unknown,
): string {
  switch (metric) {
    case "summary.total_heat_demand_mwh":
    case "summary.connected_heat_demand_mwh":
    case "summary.disconnected_heat_demand_mwh":
    case "summary.technology_annual_energy_mwh":
    case "summary.total_heat_production_mwh":
    case "candidate.annual_heat_demand_mwh":
    case "candidate.technology_annual_energy_mwh":
    case "candidate.total_heat_production_mwh":
    case "cluster.total_demand_mwh":
      return formatMwh(value);
    case "summary.connected_buildings":
    case "candidate.buildings":
    case "cluster.n_buildings": {
      const formatted = formatNumber(value);
      return formatted === "—" ? formatted : `${formatted} buildings`;
    }
    case "summary.total_annualized_eur":
    case "summary.supply_annualized_eur":
    case "summary.grid_annualized_eur":
    case "candidate.central_cost":
    case "candidate.decentral_cost":
    case "candidate.decision_margin":
    case "candidate.cost_breakdown_investment":
    case "candidate.cost_breakdown_fixed_om":
    case "candidate.cost_breakdown_operational":
    case "cluster.scaled_annualized_cost_eur":
      return formatEuro(value);
    case "summary.cost_per_connected_mwh":
      return formatEuroPerMwh(value);
    case "summary.grid_raw_total_eur":
    case "candidate.central_grid_cost_raw":
      return formatEuroCapital(value);
    case "summary.connected_share_pct":
    case "summary.supply_share_pct":
    case "summary.grid_share_pct":
    case "summary.technology_energy_share_pct":
      return percent(value);
    case "summary.total_network_length_m":
    case "candidate.total_network_length_m":
    case "candidate.connection_length_m":
      return unitNumber(value, "m");
    case "summary.peak_load_kw":
    case "candidate.peak_load_kw":
      return unitNumber(value, "kW", 1);
    case "candidate.average_lhd":
      return unitNumber(value, "MWh/(m·a)", 2);
    case "candidate.decision_step": {
      const formatted = formatNumber(value);
      return formatted === "—" ? formatted : `${formatted} step`;
    }
    case "candidate.storage_capacity_kwh":
      return unitNumber(value, "kWh", 1);
    case "candidate.storage_power_kw":
      return unitNumber(value, "kW", 1);
    case "summary.technology_capacity_kw":
      return unitNumber(value, "kW", 1);
    default:
      return formatNumber(value, 1);
  }
}

function unitNumber(value: unknown, unit: string, digits = 0): string {
  const formatted = formatNumber(value, digits);
  return formatted === "—" ? formatted : `${formatted} ${unit}`;
}

function percent(value: unknown): string {
  const formatted = formatNumber(value, 1);
  return formatted === "—" ? formatted : `${formatted}%`;
}

/**
 * The contract is available without making a reader leave the result. The
 * disclosure keeps the map/table compact while making scope, basis, stage,
 * and source artifact explicit when a value needs to be audited.
 */
export function MetricDefinitionDisclosure({
  metric,
  label = "Metric definition",
}: {
  metric: ResultMetricId;
  label?: string;
}) {
  useLocale();
  const definition = metricDefinition(metric);
  const [open, setOpen] = useState(false);
  return (
    <details className="metric-definition">
      <summary onClick={() => setOpen((value) => !value)}>{tr(label)}</summary>
      {open && (
        <Box component="dl" sx={{ m: 0, mt: 0.75 }}>
          <MetricDefinitionRow label={tr("Unit")} value={definition.unit} />
          <MetricDefinitionRow label={tr("Scope")} value={definition.scope} />
          <MetricDefinitionRow
            label={tr("Time basis")}
            value={definition.timeBasis}
          />
          <MetricDefinitionRow
            label={tr("Calculation stage")}
            value={definition.calculationStage}
          />
          <MetricDefinitionRow label={tr("Basis")} value={definition.basis} />
          <MetricDefinitionRow
            label={tr("Provenance")}
            value={definition.provenance.join(" · ")}
          />
        </Box>
      )}
    </details>
  );
}

/** A single disclosure is useful in an inspector with many related values. */
export function MetricDefinitionsDisclosure({
  metrics,
  label = "Metric definitions & provenance",
}: {
  metrics: ResultMetricId[];
  label?: string;
}) {
  useLocale();
  const uniqueMetrics = [...new Set(metrics)];
  const [open, setOpen] = useState(false);
  return (
    <details className="metric-definitions">
      <summary onClick={() => setOpen((value) => !value)}>{tr(label)}</summary>
      {open && (
        <Stack spacing={1} sx={{ mt: 1 }}>
          {uniqueMetrics.map((metric) => {
            const definition = metricDefinition(metric);
            return (
              <Box key={metric} component="section">
                <Typography fontWeight={600} variant="body2">
                  {tr(metric)}
                </Typography>
                <Typography color="text.secondary" variant="caption">
                  {tr(definition.unit)} · {tr(definition.scope)} ·{tr(" ")}
                  {tr(definition.timeBasis)} · {tr(definition.calculationStage)}{" "}
                  ·{tr(" ")}
                  {tr(definition.basis)} {tr(" · source:")}
                  {tr(" ")}
                  {tr(definition.provenance.join(", "))}
                </Typography>
              </Box>
            );
          })}
        </Stack>
      )}
    </details>
  );
}

function MetricDefinitionRow({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  useLocale();
  return (
    <Stack component="div" direction="row" spacing={1} sx={{ mb: 0.25 }}>
      <Typography component="dt" color="text.secondary" variant="caption">
        {tr(label)}
      </Typography>
      <Typography component="dd" sx={{ m: 0 }} variant="caption">
        {tr(value)}
      </Typography>
    </Stack>
  );
}

export function MetricValue({
  label,
  metric,
  value,
}: {
  label: string;
  metric: ResultMetricId;
  value: unknown;
}) {
  useLocale();
  return (
    <Stack spacing={0.25}>
      <Typography color="text.secondary" variant="body2">
        {tr(label)}
      </Typography>
      <Typography fontWeight={600} sx={{ fontVariantNumeric: "tabular-nums" }}>
        {tr(formatMetricValue(metric, value))}
      </Typography>
      <MetricDefinitionDisclosure metric={metric} />
    </Stack>
  );
}
