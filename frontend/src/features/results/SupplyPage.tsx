import { tr } from "../../i18n/translate";

import { useLocale } from "../../i18n/locale";

import {
  Button,
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

import {
  useResultSupplyQuery,
  useResultTimeseriesQuery,
} from "../../api/queries";

import {
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";

import { AccessibleBarChart } from "./AccessibleBarChart";

import { ResultUnavailable, ResultWarnings } from "./ResultFeedback";

import { formatMwh, formatNumber } from "./format";

export function SupplyPage({ runId }: { runId: string }) {
  useLocale();

  const supply = useResultSupplyQuery(runId);

  const [loadTimeseries, setLoadTimeseries] = useState(false);

  const timeseries = useResultTimeseriesQuery(runId, loadTimeseries, {
    resolution: 2_000,
  });

  if (supply.isPending)
    return <LoadingState label={tr("Loading supply portfolio…")} />;

  if (supply.isError)
    return (
      <FailureState
        error={supply.error}

        onRetry={() => void supply.refetch()}
      />
    );

  if (!supply.data?.available || !supply.data.data) {
    return (
      <ResultUnavailable
        warnings={supply.data?.warnings}

        title={tr("Supply portfolio unavailable")}
      />
    );
  }

  const result = supply.data.data;

  const technologies = Object.entries(result.supply ?? {});

  const technologyChart = technologies.map(([name, technology]) => ({
    label: name.replaceAll("_", " "),

    value: technology.annual_energy_mwh ?? technology.annual_heat_energy_mwh,
  }));

  const capacityChart = technologies.map(([name, technology]) => ({
    label: name.replaceAll("_", " "),

    value:
      technology.capacity_kw ??
      technology.capacity_th_kw ??
      technology.capacity_el_kw,
  }));

  return (
    <Stack spacing={2}>
      <Typography component="h2" variant="h5">
        {tr("Supply portfolio")}
      </Typography>

      <ResultWarnings warnings={supply.data.warnings} />

      <Paper
        component="section"

        elevation={0}

        sx={{ border: 1, borderColor: "divider", overflowX: "auto" }}
      >
        <Table aria-label={tr("Supply technology portfolio")}>
          <TableHead>
            <TableRow>
              <TableCell>{tr("Technology")}</TableCell>

              <TableCell align="right">{tr("Capacity")}</TableCell>

              <TableCell align="right">{tr("Annual heat")}</TableCell>

              <TableCell align="right">{tr("Energy share")}</TableCell>
            </TableRow>
          </TableHead>

          <TableBody>
            {technologies.map(([name, technology]) => (
              <TableRow key={name}>
                <TableCell>{tr(name.replaceAll("_", " "))}</TableCell>

                <TableCell align="right">
                  {tr(
                    formatNumber(
                      technology.capacity_kw ??
                        technology.capacity_th_kw ??
                        technology.capacity_el_kw,

                      1,
                    ),
                  )}

                  {tr(" ")}

                  {tr("kW")}
                </TableCell>

                <TableCell align="right">
                  {tr(
                    formatMwh(
                      technology.annual_energy_mwh ??
                        technology.annual_heat_energy_mwh,
                    ),
                  )}
                </TableCell>

                <TableCell align="right">
                  {tr(formatNumber(technology.energy_share_pct, 1))}%
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>

        {!technologies.length && (
          <Typography color="text.secondary" sx={{ p: 2 }}>
            {tr("No supply technologies were reported.")}
          </Typography>
        )}
      </Paper>

      <AccessibleBarChart
        data={capacityChart}

        formatValue={(value) => `${formatNumber(value, 1)} kW`}

        title={tr("Installed capacity by technology")}

        valueLabel="Capacity (kW)"
      />

      <AccessibleBarChart
        data={technologyChart}

        formatValue={(value) => formatMwh(value)}

        title={tr("Annual heat production by technology")}

        valueLabel="Heat (MWh/a)"
      />

      <StorageSection result={result} />

      <ResourceUtilization result={result} />

      <Paper
        component="section"

        elevation={0}

        sx={{ border: 1, borderColor: "divider", p: 2 }}
      >
        <Stack
          alignItems={{ sm: "center", xs: "flex-start" }}

          direction={{ sm: "row", xs: "column" }}

          justifyContent="space-between"

          spacing={1}
        >
          <BoxHeading
            body={tr(
              "Optional hourly or sub-hourly series are loaded only when requested.",
            )}

            title={tr("Supply time series")}
          />

          <Button
            disabled={loadTimeseries && timeseries.isPending}

            onClick={() => setLoadTimeseries(true)}

            variant="outlined"
          >
            {tr(loadTimeseries ? "Refresh time series" : "Load time series")}
          </Button>
        </Stack>

        {loadTimeseries && timeseries.isPending && (
          <LoadingState label={tr("Loading bounded time series…")} />
        )}

        {loadTimeseries && timeseries.isError && (
          <FailureState
            error={timeseries.error}

            onRetry={() => void timeseries.refetch()}
          />
        )}

        {loadTimeseries && timeseries.data && (
          <TimeSeriesSummary result={timeseries.data} />
        )}
      </Paper>
    </Stack>
  );
}

function StorageSection({
  result,
}: {
  result: import("../../api/results").SupplyResult;
}) {
  useLocale();

  const storage = Object.entries(result.storage ?? {});

  return (
    <Paper
      component="section"

      elevation={0}

      sx={{ border: 1, borderColor: "divider", overflowX: "auto", p: 2 }}
    >
      <Typography component="h2" gutterBottom variant="h6">
        {tr("Storage")}
      </Typography>

      {!storage.length ? (
        <Typography color="text.secondary">
          {tr("No storage was reported.")}
        </Typography>
      ) : (
        <Table aria-label={tr("Storage capacity and power")} size="small">
          <TableHead>
            <TableRow>
              <TableCell>{tr("Storage")}</TableCell>

              <TableCell align="right">{tr("Capacity")}</TableCell>

              <TableCell align="right">{tr("Power")}</TableCell>
            </TableRow>
          </TableHead>

          <TableBody>
            {storage.map(([name, value]) => (
              <TableRow key={name}>
                <TableCell>{tr(name.replaceAll("_", " "))}</TableCell>

                <TableCell align="right">
                  {tr(formatNumber(value.capacity_kwh, 1))} {tr(" kWh")}
                </TableCell>

                <TableCell align="right">
                  {tr(formatNumber(value.power_kw, 1))} {tr(" kW")}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Typography color="text.secondary" sx={{ mt: 2 }}>
        {tr("Total heat production: ")}

        {tr(formatMwh(result.total_heat_production_mwh))}
      </Typography>
    </Paper>
  );
}

function ResourceUtilization({
  result,
}: {
  result: import("../../api/results").SupplyResult;
}) {
  useLocale();

  const resources = result.resources;

  if (!resources || typeof resources !== "object") {
    return <ResultUnavailable title={tr("Resource utilization unavailable")} />;
  }

  type ResourceRow = {
    name: string;

    used: number | undefined;

    limit: number | undefined;

    pct: number | undefined;
  };

  const rows: ResourceRow[] = Object.entries(
    resources as Record<string, unknown>,
  ).flatMap(([name, value]) => {
    if (!value || typeof value !== "object") return [];

    const item = value as Record<string, unknown>;

    const used = number(item.used ?? item.used_mwh ?? item.utilized);

    const limit = number(item.limit ?? item.limit_mwh ?? item.available);

    const pct =
      number(item.utilization_pct) ??
      (used !== undefined && limit ? (used / limit) * 100 : undefined);

    if (used === undefined && limit === undefined && pct === undefined)
      return [];

    return [{ name, used, limit, pct }];
  });

  if (!rows.length)
    return <ResultUnavailable title={tr("Resource utilization unavailable")} />;

  return (
    <Paper
      component="section"

      elevation={0}

      sx={{ border: 1, borderColor: "divider", overflowX: "auto", p: 2 }}
    >
      <Typography component="h2" gutterBottom variant="h6">
        {tr("Resource utilization")}
      </Typography>

      <Table aria-label={tr("Resource utilization")} size="small">
        <TableHead>
          <TableRow>
            <TableCell>{tr("Resource")}</TableCell>

            <TableCell align="right">{tr("Used")}</TableCell>

            <TableCell align="right">{tr("Limit")}</TableCell>

            <TableCell align="right">{tr("Utilization")}</TableCell>
          </TableRow>
        </TableHead>

        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.name}>
              <TableCell>{tr(row.name.replaceAll("_", " "))}</TableCell>

              <TableCell align="right">
                {tr(formatNumber(row.used, 1))}
              </TableCell>

              <TableCell align="right">
                {tr(formatNumber(row.limit, 1))}
              </TableCell>

              <TableCell align="right">
                {tr(formatNumber(row.pct, 1))}%
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Paper>
  );
}

function TimeSeriesSummary({
  result,
}: {
  result: {
    available: boolean;

    data: import("../../api/results").TimeSeriesResult | null;

    warnings: string[];
  };
}) {
  useLocale();

  if (!result.available || !result.data) {
    return (
      <ResultUnavailable
        title={tr("Time series unavailable")}

        warnings={result.warnings}
      />
    );
  }

  const data = result.data;

  return (
    <Stack spacing={1} sx={{ mt: 2 }}>
      <Typography color="text.secondary" variant="body2">
        {tr("Showing ")}
        {tr(formatNumber(data.returned_points))} {tr(" of")}
        {tr(" ")}
        {tr(formatNumber(data.original_points))} {tr(" points")}
        {tr(data.downsampled ? " (server-side sampled)" : "")}.
      </Typography>

      <Table aria-label={tr("Supply time-series data")} size="small">
        <TableHead>
          <TableRow>
            <TableCell>{tr("Timestamp")}</TableCell>

            {data.series_names.map((name) => (
              <TableCell align="right" key={name}>
                {tr(name)}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>

        <TableBody>
          {data.points.slice(0, 100).map((point, index) => (
            <TableRow
              key={`${String(point.timestamp ?? point.time ?? index)}-${index}`}
            >
              <TableCell>
                {tr(String(point.timestamp ?? point.time ?? "—"))}
              </TableCell>

              {data.series_names.map((name) => (
                <TableCell align="right" key={name}>
                  {tr(formatNumber(point[name], 2))}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Stack>
  );
}

function BoxHeading({ title, body }: { title: string; body: string }) {
  useLocale();

  return (
    <Stack spacing={0.25}>
      <Typography component="h2" variant="h6">
        {tr(title)}
      </Typography>

      <Typography color="text.secondary" variant="body2">
        {tr(body)}
      </Typography>
    </Stack>
  );
}

function number(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : undefined;
}
