import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
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
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import {
  useResultCandidatesQuery,
  useResultDecentralQuery,
} from "../../api/queries";
import type { DecentralCandidateRecord } from "../../api/results";
import {
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";
import { ResultUnavailable, ResultWarnings } from "./ResultFeedback";
import { CandidateInspector } from "./CandidateTable";
import { formatEuro, formatMwh, formatNumber } from "./format";
import { useResultSelection } from "./selection";

export function DecentralPage({ runId }: { runId: string }) {
  useLocale();
  const decentral = useResultDecentralQuery(runId);
  // The candidate endpoint is retained as a compatibility fallback for older
  // output folders that predate the dedicated decentralized adapter.
  const candidates = useResultCandidatesQuery(runId);
  const { candidateId: selectedId, selectCandidate } = useResultSelection();
  const [decisionFilter, setDecisionFilter] = useState<
    "all" | "connected" | "rejected"
  >("all");
  const [minimumMargin, setMinimumMargin] = useState("");

  if (decentral.isPending || candidates.isPending)
    return <LoadingState label={tr("Loading decentralized comparison…")} />;
  if (decentral.isError && candidates.isError)
    return (
      <FailureState
        error={decentral.error ?? candidates.error}
        onRetry={() => {
          void decentral.refetch();
          void candidates.refetch();
        }}
      />
    );

  const records =
    decentral.data?.available && decentral.data.data
      ? decentral.data.data
      : candidates.data?.available && candidates.data.data
        ? candidates.data.data.map((item) => ({
            ...item,
            difference_eur: differenceFor(item),
            clusters_available: Boolean(item.clusters?.length),
          }))
        : [];
  if (!records.length) {
    return (
      <ResultUnavailable
        warnings={[
          ...(decentral.data?.warnings ?? []),
          ...(candidates.data?.warnings ?? []),
        ]}
        title={tr("Decentralized comparison unavailable")}
      />
    );
  }

  const threshold = minimumMargin === "" ? null : Number(minimumMargin);
  const filtered = records.filter((candidate) => {
    if (decisionFilter !== "all" && candidate.decision !== decisionFilter)
      return false;
    if (threshold !== null && Number.isFinite(threshold)) {
      const margin = differenceFor(candidate);
      if (margin === undefined || Math.abs(margin) < threshold) return false;
    }
    return true;
  });
  const selected =
    records.find((candidate) => candidate.id === selectedId) ?? null;

  return (
    <Stack spacing={2}>
      <Typography component="h2" variant="h5">
        {tr("Decentralized comparison")}
      </Typography>
      <ResultWarnings
        warnings={[
          ...(decentral.data?.warnings ?? []),
          ...(candidates.data?.warnings ?? []),
        ]}
      />
      <Paper
        component="section"
        elevation={0}
        sx={{ border: 1, borderColor: "divider", p: 2 }}
      >
        <Stack direction={{ sm: "row", xs: "column" }} spacing={2}>
          <FormControl size="small" sx={{ minWidth: 180 }}>
            <InputLabel id="decentral-decision-filter-label">
              {tr("Decision")}
            </InputLabel>
            <Select
              label={tr("Decision")}
              labelId="decentral-decision-filter-label"
              onChange={(event) =>
                setDecisionFilter(event.target.value as typeof decisionFilter)
              }
              value={decisionFilter}
            >
              <MenuItem value="all">{tr("All candidates")}</MenuItem>
              <MenuItem value="connected">{tr("Connected")}</MenuItem>
              <MenuItem value="rejected">{tr("Rejected")}</MenuItem>
            </Select>
          </FormControl>
          <TextField
            helperText={tr("Absolute cost margin in €/a")}
            label={tr("Minimum margin")}
            onChange={(event) => setMinimumMargin(event.target.value)}
            size="small"
            type="number"
            value={minimumMargin}
          />
        </Stack>
      </Paper>
      <Paper
        component="section"
        elevation={0}
        sx={{ border: 1, borderColor: "divider", overflowX: "auto" }}
      >
        <Table
          aria-label={tr("Central and decentralized candidate comparison")}
          size="small"
        >
          <TableHead>
            <TableRow>
              <TableCell>{tr("Candidate")}</TableCell>
              <TableCell>{tr("Status")}</TableCell>
              <TableCell align="right">{tr("Demand")}</TableCell>
              <TableCell align="right">{tr("Central")}</TableCell>
              <TableCell align="right">{tr("Decentralized")}</TableCell>
              <TableCell align="right">{tr("Difference")}</TableCell>
              <TableCell>{tr("Clusters")}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filtered.map((candidate) => {
              const difference = differenceFor(candidate);
              return (
                <TableRow
                  hover
                  key={candidate.id}
                  onClick={() => selectCandidate(candidate.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      selectCandidate(candidate.id);
                    }
                  }}
                  selected={candidate.id === selectedId}
                  tabIndex={0}
                  sx={{ cursor: "pointer" }}
                >
                  <TableCell>#{tr(candidate.id)}</TableCell>
                  <TableCell>{tr(candidate.decision)}</TableCell>
                  <TableCell align="right">
                    {tr(formatMwh(candidate.annual_heat_demand_mwh))}
                  </TableCell>
                  <TableCell align="right">
                    {tr(formatEuro(candidate.central_cost))}
                  </TableCell>
                  <TableCell align="right">
                    {tr(formatEuro(candidate.decentral_cost))}
                  </TableCell>
                  <TableCell align="right">
                    {tr(formatEuro(difference))}
                  </TableCell>
                  <TableCell>
                    {tr(
                      candidate.clusters_available === false
                        ? "Unavailable"
                        : formatNumber(candidate.clusters?.length),
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        {!filtered.length && (
          <Typography color="text.secondary" sx={{ p: 2 }}>
            {tr("No candidates match these filters.")}
          </Typography>
        )}
      </Paper>
      {selected && (
        <Grid container spacing={2}>
          <Grid item md={4} xs={12}>
            <CandidateInspector candidate={selected} />
          </Grid>
          <Grid item md={8} xs={12}>
            <ClusterDetails candidate={selected} />
          </Grid>
        </Grid>
      )}
    </Stack>
  );
}

function ClusterDetails({
  candidate,
}: {
  candidate: DecentralCandidateRecord;
}) {
  useLocale();
  const clusters = candidate.clusters ?? [];
  return (
    <Paper
      component="section"
      elevation={0}
      sx={{ border: 1, borderColor: "divider", overflowX: "auto" }}
    >
      <Typography component="h2" sx={{ p: 2, pb: 1 }} variant="h6">
        {tr("Decentralized clusters for #")}
        {tr(candidate.id)}
      </Typography>
      {!clusters.length ? (
        <Typography color="text.secondary" sx={{ p: 2 }}>
          {tr("Cluster details are unavailable for this candidate.")}
        </Typography>
      ) : (
        <Table
          aria-label={tr(
            `Decentralized clusters for candidate ${candidate.id}`,
          )}
          size="small"
        >
          <TableHead>
            <TableRow>
              <TableCell>{tr("Cluster")}</TableCell>
              <TableCell align="right">{tr("Buildings")}</TableCell>
              <TableCell align="right">{tr("Demand")}</TableCell>
              <TableCell align="right">{tr("Scaled cost")}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {clusters.map((cluster, index) => (
              <TableRow key={String(cluster.cluster_id ?? index)}>
                <TableCell>
                  {tr(String(cluster.cluster_id ?? index + 1))}
                </TableCell>
                <TableCell align="right">
                  {tr(formatNumber(cluster.n_buildings))}
                </TableCell>
                <TableCell align="right">
                  {tr(formatMwh(cluster.total_demand_mwh))}
                </TableCell>
                <TableCell align="right">
                  {tr(formatEuro(cluster.scaled_annualized_cost_eur))}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Paper>
  );
}

function differenceFor(candidate: {
  central_cost?: number;
  decentral_cost?: number;
  difference_eur?: number;
}): number | undefined {
  if (typeof candidate.difference_eur === "number")
    return candidate.difference_eur;
  if (
    typeof candidate.central_cost !== "number" ||
    typeof candidate.decentral_cost !== "number"
  )
    return undefined;
  return candidate.decentral_cost - candidate.central_cost;
}
