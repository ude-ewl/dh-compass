import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
  Button,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  useResultCandidatesQuery,
  useResultIterationsQuery,
  useResultNetworkQuery,
} from "../../api/queries";
import {
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";
import type { FeatureCollection, IterationRecord } from "../../api/results";
import { AccessibleBarChart } from "./AccessibleBarChart";
import { ResultUnavailable, ResultWarnings } from "./ResultFeedback";
import { CandidateInspector } from "./CandidateTable";
import { formatEuro, formatMwh, formatNumber } from "./format";
import { ResultMap } from "./ResultMap";
import { useResultSelection } from "./selection";

export function DecisionsPage({ runId }: { runId: string }) {
  useLocale();
  const iterations = useResultIterationsQuery(runId);
  const network = useResultNetworkQuery(runId, [
    "final_network",
    "candidate_network",
    "connection_paths",
  ]);
  const candidates = useResultCandidatesQuery(runId);
  const { candidateId, iterationIndex, selectResult } = useResultSelection();
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);

  const records = useMemo(
    () => (iterations.data?.available ? (iterations.data.data ?? []) : []),
    [iterations.data],
  );
  const candidateStep =
    candidateId === null
      ? -1
      : records.findIndex((record) => record.subgraph_id === candidateId);
  const requestedStep =
    iterationIndex ?? (candidateStep >= 0 ? candidateStep : 0);
  const currentStep = Math.min(
    Math.max(requestedStep, 0),
    Math.max(records.length - 1, 0),
  );
  const current = records[currentStep];

  const selectStep = useCallback(
    (value: number) => {
      const selected = records[value];
      if (!selected) return;
      selectResult({ candidate: selected.subgraph_id, iteration: value });
    },
    [records, selectResult],
  );

  useEffect(() => {
    if (!playing || records.length === 0) return;
    const timer = window.setInterval(() => {
      const next = currentStep + 1;
      if (next >= records.length) {
        setPlaying(false);
        return;
      }
      selectStep(next);
    }, 900 / speed);
    return () => window.clearInterval(timer);
  }, [currentStep, playing, records, selectStep, speed]);

  if (iterations.isPending || network.isPending || candidates.isPending) {
    return <LoadingState label={tr("Loading decision playback…")} />;
  }
  if (iterations.isError)
    return (
      <FailureState
        error={iterations.error}
        onRetry={() => void iterations.refetch()}
      />
    );
  if (network.isError) return <FailureState error={network.error} />;
  if (!iterations.data?.available || !current) {
    return (
      <ResultUnavailable
        warnings={iterations.data?.warnings}
        title={tr("Decision playback unavailable")}
      />
    );
  }

  const candidateData =
    candidates.data?.available && candidates.data.data
      ? candidates.data.data
      : [];
  // The playback step is the single selection authority on this route.  Map
  // clicks therefore jump to the corresponding decision rather than leaving
  // the map, inspector, chart, and table on different candidates.
  const candidate =
    candidateData.find((item) => item.id === current.subgraph_id) ?? null;
  const candidateLayers = network.data?.data?.candidate_network;
  const connectedIds = new Set(current.cumulative_connected_ids ?? []);
  const playbackCandidates: FeatureCollection | null = candidateLayers
    ? {
        ...candidateLayers,
        features: candidateLayers.features.map((feature) => {
          const id = feature.properties?.candidate_id;
          const candidateIdValue = typeof id === "number" ? id : null;
          return {
            ...feature,
            properties: {
              ...(feature.properties ?? {}),
              decision:
                candidateIdValue === current.subgraph_id
                  ? "current"
                  : candidateIdValue !== null &&
                      connectedIds.has(candidateIdValue)
                    ? "connected"
                    : "rejected",
            },
          };
        }),
      }
    : null;
  const paths = network.data?.data?.connection_paths;
  const visiblePaths: FeatureCollection | null = paths
    ? {
        ...paths,
        features: paths.features.filter((feature) => {
          const value = feature.properties?.step;
          return (
            feature.properties?.decision === "connected" &&
            (typeof value !== "number" || value <= current.step)
          );
        }),
      }
    : null;

  return (
    <Stack spacing={2}>
      <Typography component="h2" variant="h5">
        {tr("Decision playback")}
      </Typography>
      <ResultWarnings
        warnings={[
          ...(iterations.data.warnings ?? []),
          ...(network.data?.warnings ?? []),
        ]}
      />
      <Paper
        component="section"
        elevation={0}
        sx={{ border: 1, borderColor: "divider", p: 2 }}
      >
        <Stack
          alignItems={{ md: "center", xs: "stretch" }}
          direction={{ md: "row", xs: "column" }}
          spacing={1}
        >
          <Button onClick={() => selectStep(0)} variant="outlined">
            {tr("First")}
          </Button>
          <Button
            onClick={() => selectStep(Math.max(0, currentStep - 1))}
            variant="outlined"
          >
            {tr("Previous")}
          </Button>
          <Button
            onClick={() => setPlaying((value) => !value)}
            variant="contained"
          >
            {tr(playing ? "Pause" : "Play")}
          </Button>
          <Button
            onClick={() =>
              selectStep(Math.min(records.length - 1, currentStep + 1))
            }
            variant="outlined"
          >
            {tr("Next")}
          </Button>
          <Button
            onClick={() => selectStep(records.length - 1)}
            variant="outlined"
          >
            {tr("Last")}
          </Button>
          <input
            aria-label={tr("Decision playback step")}
            max={records.length - 1}
            min={0}
            onChange={(event) => selectStep(Number(event.target.value))}
            style={{ flex: 1, minWidth: 120 }}
            type="range"
            value={currentStep}
          />
          <Typography sx={{ minWidth: 135 }}>
            {tr("Step ")}
            {tr(currentStep + 1)} / {tr(records.length)} {tr(" · Candidate #")}
            {tr(current.subgraph_id)}
          </Typography>
          <FormControl size="small" sx={{ minWidth: 110 }}>
            <InputLabel id="playback-speed-label">{tr("Speed")}</InputLabel>
            <Select
              label={tr("Speed")}
              labelId="playback-speed-label"
              onChange={(event) => setSpeed(Number(event.target.value))}
              value={speed}
            >
              <MenuItem value={0.5}>0.5×</MenuItem>
              <MenuItem value={1}>1×</MenuItem>
              <MenuItem value={2}>2×</MenuItem>
            </Select>
          </FormControl>
        </Stack>
      </Paper>
      <Grid container spacing={2}>
        <Grid item md={8} xs={12}>
          <ResultMap
            candidateNetwork={playbackCandidates}
            connectionPaths={visiblePaths}
            finalNetwork={network.data?.data?.final_network}
            lhd={network.data?.data?.lhd}
            onSelectCandidate={(value) => {
              const step = records.findIndex(
                (record) => record.subgraph_id === value,
              );
              if (step >= 0) selectStep(step);
            }}
            selectedCandidateId={current.subgraph_id}
            title={tr("Decision playback map")}
          />
        </Grid>
        <Grid item md={4} xs={12}>
          <DecisionSummary iteration={current} />
          <CandidateInspector candidate={candidate} />
        </Grid>
      </Grid>
      <AccessibleBarChart
        data={[
          {
            label: "Marginal central cost",
            value: current.marginal_central_cost,
          },
          { label: "Decentralized cost", value: current.decentral_cost },
        ]}
        formatValue={(value) => formatEuro(value)}
        title={tr(`Costs for candidate #${current.subgraph_id}`)}
        valueLabel="Annualized cost (€/a)"
      />
      <IterationTable
        records={records}
        selectedStep={currentStep}
        onSelect={selectStep}
      />
    </Stack>
  );
}

function DecisionSummary({ iteration }: { iteration: IterationRecord }) {
  useLocale();
  const connected = iteration.decision === "connected";
  const supply = iteration.cumulative_supply;
  return (
    <Paper
      component="section"
      elevation={0}
      sx={{ border: 1, borderColor: "divider", mb: 2, p: 2 }}
    >
      <Typography component="h2" gutterBottom variant="h6">
        {tr("Candidate #")}
        {tr(iteration.subgraph_id)}
      </Typography>
      <Stack spacing={1}>
        <Typography>
          {tr("Decision: ")}
          <strong>{tr(connected ? "Connected" : "Rejected")}</strong>
        </Typography>
        <Metric
          label={tr("Marginal central")}
          value={formatEuro(iteration.marginal_central_cost)}
        />
        <Metric
          label={tr("Decentralized")}
          value={formatEuro(iteration.decentral_cost)}
        />
        <Metric
          label={tr("Cumulative central")}
          value={formatEuro(iteration.central_cost_total)}
        />
        <Metric
          label={tr("Connected candidates")}
          value={formatNumber(iteration.cumulative_connected_ids?.length)}
        />
        {supply && (
          <Metric
            label={tr("Cumulative heat")}
            value={formatMwh(supply.total_heat_production_mwh)}
          />
        )}
      </Stack>
    </Paper>
  );
}

function IterationTable({
  records,
  selectedStep,
  onSelect,
}: {
  records: IterationRecord[];
  selectedStep: number;
  onSelect: (step: number) => void;
}) {
  useLocale();
  return (
    <Paper
      component="section"
      elevation={0}
      sx={{ border: 1, borderColor: "divider", overflowX: "auto" }}
    >
      <Typography component="h2" sx={{ p: 2, pb: 1 }} variant="h6">
        {tr("Accessible decision table")}
      </Typography>
      <Table aria-label={tr("Decision playback data")} size="small">
        <TableHead>
          <TableRow>
            <TableCell>{tr("Step")}</TableCell>
            <TableCell>{tr("Candidate")}</TableCell>
            <TableCell>{tr("Decision")}</TableCell>
            <TableCell align="right">{tr("Marginal central")}</TableCell>
            <TableCell align="right">{tr("Decentralized")}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {records.map((record, index) => (
            <TableRow
              hover
              key={`${record.step}-${record.subgraph_id}`}
              onClick={() => onSelect(index)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(index);
                }
              }}
              selected={index === selectedStep}
              tabIndex={0}
              sx={{ cursor: "pointer" }}
            >
              <TableCell>{tr(index + 1)}</TableCell>
              <TableCell>#{tr(record.subgraph_id)}</TableCell>
              <TableCell>{tr(record.decision)}</TableCell>
              <TableCell align="right">
                {tr(formatEuro(record.marginal_central_cost))}
              </TableCell>
              <TableCell align="right">
                {tr(formatEuro(record.decentral_cost))}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Paper>
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
