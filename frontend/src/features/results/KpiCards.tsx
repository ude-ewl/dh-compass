import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
  Card,
  CardActionArea,
  CardContent,
  Grid,
  Typography,
} from "@mui/material";
import { Link as RouterLink } from "react-router-dom";

import type { ResultMetricId } from "./metricContract";
import {
  formatMetricValue,
  MetricDefinitionsDisclosure,
} from "./MetricDisplay";

interface KpiCard {
  label: string;
  metrics: ResultMetricId[];
  value: string;
  detail: string;
  /** Relative destination; `null` renders the card without a link. */
  to: string | null;
}

export function KpiCards({
  summary,
  connectedBuildings,
  totalCost,
  networkLength,
  peakLoad,
  costPerConnectedMwh,
  runId,
  networkPath = "/results/network",
  costsPath = "/results/costs",
}: {
  summary: Record<string, unknown>;
  connectedBuildings?: number;
  totalCost?: number;
  networkLength?: number;
  peakLoad?: number;
  costPerConnectedMwh?: number;
  runId?: string;
  /** Destination for network values; `null` keeps the card static. */
  networkPath?: string | null;
  /** Destination for cost values; `null` when the summary already shows them. */
  costsPath?: string | null;
}) {
  useLocale();
  const cards: KpiCard[] = [
    {
      label: "Connected heat demand",
      metrics: [
        "summary.connected_heat_demand_mwh",
        "summary.connected_share_pct",
      ],
      value: formatMetricValue(
        "summary.connected_heat_demand_mwh",
        summary.connected_heat_demand_mwh,
      ),
      detail: `${formatMetricValue("summary.connected_share_pct", summary.connected_share_pct)} of total demand`,
      to: networkPath,
    },
    {
      label: "Connected buildings",
      metrics: ["summary.connected_buildings"],
      value: formatMetricValue(
        "summary.connected_buildings",
        connectedBuildings,
      ),
      detail: "served by the final central network",
      to: networkPath,
    },
    {
      label: "Total annualized cost",
      metrics: ["summary.total_annualized_eur"],
      value: formatMetricValue("summary.total_annualized_eur", totalCost),
      detail: "final connected central system · grid and supply",
      to: costsPath,
    },
    {
      label: "Network length",
      metrics: ["summary.total_network_length_m", "summary.peak_load_kw"],
      value: formatMetricValue("summary.total_network_length_m", networkLength),
      detail: `Peak load ${formatMetricValue("summary.peak_load_kw", peakLoad)}`,
      to: networkPath,
    },
  ];

  if (costPerConnectedMwh !== undefined) {
    cards.push({
      label: "Cost per connected MWh",
      metrics: ["summary.cost_per_connected_mwh"],
      value: formatMetricValue(
        "summary.cost_per_connected_mwh",
        costPerConnectedMwh,
      ),
      detail: "annualized cost ÷ connected annual demand",
      to: costsPath,
    });
  }

  return (
    <Grid container spacing={2}>
      {cards.map((card) => (
        <Grid
          item
          key={card.label}
          md={cards.length > 4 ? 2.4 : 3}
          sm={6}
          xs={12}
        >
          <Card
            elevation={0}
            sx={{ border: 1, borderColor: "divider", height: "100%" }}
          >
            {runId && card.to ? (
              <CardActionArea
                component={RouterLink}
                sx={{ height: "100%" }}
                to={`/runs/${encodeURIComponent(runId)}${card.to}`}
              >
                <KpiContent card={card} />
              </CardActionArea>
            ) : (
              <KpiContent card={card} />
            )}
            <MetricDefinitionsDisclosure metrics={card.metrics} />
          </Card>
        </Grid>
      ))}
    </Grid>
  );
}

function KpiContent({ card }: { card: KpiCard }) {
  useLocale();
  return (
    <CardContent>
      <Typography color="text.secondary" variant="overline">
        {tr(card.label)}
      </Typography>
      <Typography
        component="p"
        sx={{ fontVariantNumeric: "tabular-nums", mt: 0.5 }}
        variant="h5"
      >
        {tr(card.value)}
      </Typography>
      <Typography color="text.secondary" variant="body2">
        {tr(card.detail)}
      </Typography>
    </CardContent>
  );
}
