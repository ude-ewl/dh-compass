import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
  Box,
  Grid,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { EChart } from "../../components/charts/EChart";
import type { EChartsOption } from "echarts";
import { useResultCostsQuery, useResultSupplyQuery } from "../../api/queries";
import {
  ResultPanelError,
  ResultPanelLoading,
  ResultPanelUnavailable,
} from "./ResultPanel";
import {
  costSegments,
  finite,
  technologyData,
  technologyLabel,
} from "./combinedGridCharts";
import { formatEuro, formatMwh, formatNumber } from "./format";
import { AccessibleBarChart } from "./AccessibleBarChart";

const generationColors = [
  "#4992ff",
  "#7cffb2",
  "#fddd60",
  "#ff6e76",
  "#58d9f9",
  "#b79eff",
  "#ffb980",
  "#a6c84c",
];

export function CombinedGridResults({
  runId,
  summary,
}: {
  runId: string;
  summary: Record<string, unknown>;
}) {
  useLocale();
  const costs = useResultCostsQuery(runId);
  const supply = useResultSupplyQuery(runId);
  const metrics = [
    ["Annual demand", formatMwh(summary.connected_heat_demand_mwh)],
    ["Peak load", unit(summary.peak_load_kw, "kW")],
    ["Buildings", formatNumber(summary.connected_buildings)],
    ["Connection length", unit(summary.final_connection_length_m, "m")],
    [
      "Average LHD",
      unit(summary.average_linear_heat_density_mwh_per_m_a, "MWh/m/a", 3),
    ],
    ["Total annualized cost", formatEuro(summary.total_annualized_eur)],
  ];
  const costData = costs.data?.available ? costs.data.data : null;
  const supplyData = supply.data?.available ? supply.data.data : null;
  const segments = costData ? costSegments(costData) : [];
  const completeCosts =
    segments.length > 0 &&
    segments.every((segment) =>
      segment.values.every((value) => value !== undefined),
    );
  const technologies = supplyData ? technologyData(supplyData) : [];
  const generation = technologies.filter(
    (item) => item.energy !== undefined && item.energy > 0,
  );
  const energyTotal = generation.reduce(
    (total, item) => total + (item.energy ?? 0),
    0,
  );
  const resources = Object.entries(supplyData?.resources ?? {});
  const costOption: EChartsOption = {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      appendToBody: true,
      confine: true,
      // Keep tooltips inside the viewport immediately after a resize.
      transitionDuration: 0,
      extraCssText:
        "max-width: min(240px, calc(100vw - 80px)); white-space: normal; z-index: 1500;",
      formatter: (params) => {
        const hovered = Array.isArray(params) ? params[0] : params;
        const infrastructure = hovered.dataIndex === 0;
        const tooltip = document.createElement("div");
        tooltip.setAttribute("role", "tooltip");
        const heading = document.createElement("strong");
        heading.textContent = tr(infrastructure ? "Infrastructure" : "Supply");
        tooltip.append(heading);
        segments
          .slice(infrastructure ? 0 : 4, infrastructure ? 4 : 7)
          .forEach((segment) => {
            const row = document.createElement("div");
            row.style.marginTop = "6px";
            row.textContent = `${segment.name}: ${formatEuro(segment.values[infrastructure ? 0 : 1])}`;
            tooltip.append(row);
          });
        return tooltip;
      },
    },
    legend: { show: false },
    grid: { left: 70, right: 16, top: 32, bottom: 40 },
    xAxis: { type: "category", data: [tr("Infrastructure"), tr("Supply")] },
    yAxis: {
      type: "value",
      name: "€/a",
      axisLabel: { formatter: (value: number) => formatNumber(value) },
    },
    series: segments.map((segment) => ({
      name: segment.name,
      type: "bar",
      stack: "cost",
      data: segment.values.map((value) => value ?? null),
      itemStyle: { color: segment.color },
    })),
  };
  return (
    <Stack spacing={2} className="printable-results">
      <Typography component="h2" variant="h6">
        {tr("Key results")}
      </Typography>
      <Grid container spacing={1}>
        {metrics.map(([label, value]) => (
          <Grid item xs={6} key={label}>
            <Paper variant="outlined" sx={{ p: 1.5, height: "100%" }}>
              <Typography color="text.secondary" variant="body2">
                {tr(label)}
              </Typography>
              <Typography fontWeight={600}>{tr(value)}</Typography>
            </Paper>
          </Grid>
        ))}
      </Grid>
      {costs.isPending ? (
        <ResultPanelLoading label={tr("Loading costs…")} />
      ) : costs.isError ? (
        <ResultPanelError
          title={tr("Costs unavailable")}
          error={costs.error}
          onRetry={() => void costs.refetch()}
        />
      ) : !completeCosts ? (
        <ResultPanelUnavailable
          title={tr("Cost breakdown unavailable")}
          warnings={costs.data?.warnings}
        />
      ) : (
        <ChartPanel title={tr("Annualized cost breakdown")}>
          <Chart title={tr("Annualized cost breakdown")} option={costOption} />
          <Stack spacing={0.5}>
            {segments.map((segment, index) => (
              <Stack
                key={segment.name}
                direction="row"
                spacing={1}
                alignItems="center"
              >
                <Box
                  aria-hidden
                  sx={{
                    width: 10,
                    height: 10,
                    flexShrink: 0,
                    bgcolor: segment.color,
                  }}
                />
                <Typography variant="caption">
                  {tr(segment.name)}:{tr(" ")}
                  {tr(formatEuro(segment.values[index < 4 ? 0 : 1]))}
                </Typography>
              </Stack>
            ))}
          </Stack>
          <Typography variant="caption" color="text.secondary">
            {tr(
              "Investment is annualized. Variable cost uses the reported net operating cost, including electricity sales credits.",
            )}
          </Typography>
        </ChartPanel>
      )}
      {supply.isPending ? (
        <ResultPanelLoading label={tr("Loading supply…")} />
      ) : supply.isError ? (
        <ResultPanelError
          title={tr("Supply unavailable")}
          error={supply.error}
          onRetry={() => void supply.refetch()}
        />
      ) : !supplyData ? (
        <ResultPanelUnavailable
          title={tr("Supply unavailable")}
          warnings={supply.data?.warnings}
        />
      ) : (
        <>
          <AccessibleBarChart
            showDataToggle={false}
            title={tr("Installed capacities")}
            valueLabel="Thermal capacity (kW)"
            formatValue={(value) => unit(value, "kW", 1)}
            data={technologies
              .filter(
                (item) => item.capacity !== undefined && item.capacity > 0,
              )
              .map((item) => ({ label: item.name, value: item.capacity }))}
          />
          <ChartPanel title={tr("Generation mix")}>
            {generation.length === 0 ? (
              <Typography color="text.secondary">
                {tr("No heat generation was reported.")}
              </Typography>
            ) : (
              <>
                <Chart
                  title={tr("Generation mix")}
                  option={{
                    tooltip: {
                      trigger: "item",
                      valueFormatter: (value) => formatMwh(Number(value)),
                    },
                    series: [
                      {
                        type: "pie",
                        radius: "65%",
                        label: { show: false },
                        data: generation.map((item, index) => ({
                          name: item.name,
                          value: item.energy!,
                          itemStyle: {
                            color:
                              generationColors[index % generationColors.length],
                          },
                        })),
                      },
                    ],
                  }}
                />
                {generation.map((item, index) => (
                  <Stack
                    key={item.name}
                    direction="row"
                    spacing={1}
                    alignItems="center"
                  >
                    <Box
                      aria-hidden
                      sx={{
                        width: 10,
                        height: 10,
                        flexShrink: 0,
                        bgcolor:
                          generationColors[index % generationColors.length],
                      }}
                    />
                    <Typography variant="body2">
                      {tr(item.name)}: {tr(formatMwh(item.energy))} (
                      {tr(formatNumber((item.energy! / energyTotal) * 100, 1))}
                      %)
                    </Typography>
                  </Stack>
                ))}
              </>
            )}
          </ChartPanel>
          <ChartPanel title={tr("Location-dependent potential used")}>
            {resources.length === 0 ? (
              <Typography color="text.secondary">
                {tr("Resource potential was not reported for this run.")}
              </Typography>
            ) : (
              resources.map(([name, resource]) => {
                const used = finite(resource.used);
                const limit = finite(resource.limit);
                const pct =
                  used !== undefined && limit !== undefined && limit > 0
                    ? (used / limit) * 100
                    : undefined;
                return (
                  <Stack spacing={0.5} key={name}>
                    <Typography variant="body2">
                      {tr(technologyLabel(name))} ·{tr(" ")}
                      {tr(
                        pct === undefined
                          ? "Utilization unavailable"
                          : `${formatNumber(pct, 1)}% used`,
                      )}
                    </Typography>
                    {pct !== undefined && (
                      <LinearProgress
                        aria-label={tr(
                          `${technologyLabel(name)} potential used`,
                        )}
                        variant="determinate"
                        value={Math.max(0, Math.min(100, pct))}
                        color={pct > 100 ? "warning" : "primary"}
                        sx={{ height: 10, borderRadius: 1 }}
                      />
                    )}
                    <Typography color="text.secondary" variant="caption">
                      {tr(formatNumber(used, 1))} / {tr(formatNumber(limit, 1))}
                      {tr(" ")}
                      {tr(resource.unit ?? "")}
                    </Typography>
                  </Stack>
                );
              })
            )}
          </ChartPanel>
        </>
      )}
    </Stack>
  );
}

function unit(value: unknown, suffix: string, digits = 0) {
  return finite(value) === undefined
    ? "—"
    : `${formatNumber(value, digits)} ${suffix}`;
}
function ChartPanel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  useLocale();
  return (
    <Paper component="section" variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={1}>
        <Typography component="h3" variant="h6">
          {tr(title)}
        </Typography>
        {tr(children)}
      </Stack>
    </Paper>
  );
}
function Chart({ title, option }: { title: string; option: EChartsOption }) {
  useLocale();
  return (
    <Box role="img" aria-label={tr(`${title} chart; values listed below`)}>
      <EChart option={option} />
    </Box>
  );
}
