import { tr } from "../../i18n/translate";
import { formatNumericValue } from "../../i18n/number";

import { useLocale } from "../../i18n/locale";

import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useMemo, useState } from "react";

import { cancelPreview } from "../../api/client";

import type { PreviewCandidate, PreviewStatus } from "../../api/workflow";

import {
  usePreviewCandidatesQuery,
  usePreviewLayerQuery,
  usePreviewQuery,
} from "../../api/queries";

import { ApiErrorAlert } from "../../components/feedback/ApiErrorAlert";

import {
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";

import { PreviewMap } from "./PreviewMap";

interface CandidatePreviewProps {
  scenarioId: string;

  previewId: string | null;

  onGenerate: () => Promise<unknown>;

  onExpertSettings?: () => void;
}

const statusLabels: Record<PreviewStatus, string> = {
  queued: "Queued",

  running: "Running",

  cancellation_requested: "Cancellation requested",

  ready: "Ready",

  stale: "Stale",

  failed: "Failed",

  cancelled: "Cancelled",
};

function number(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "—";

  return formatNumericValue(value, { maximumFractionDigits: digits });
}

function StatusChip({ status }: { status: PreviewStatus }) {
  useLocale();

  const color =
    status === "ready"
      ? "success"
      : status === "failed" || status === "stale"
        ? "error"
        : "warning";

  return <Chip color={color} label={tr(statusLabels[status])} size="small" />;
}

function Summary({
  candidateCount,

  includedBuildings,

  demand,

  networkLength,
}: {
  candidateCount: number;

  includedBuildings: number | null | undefined;

  demand: number | null | undefined;

  networkLength: number | null | undefined;
}) {
  useLocale();

  return (
    <Stack direction={{ sm: "row", xs: "column" }} spacing={1}>
      <Paper sx={{ flex: 1, p: 2 }} variant="outlined">
        <Typography color="text.secondary" variant="caption">
          {tr("Candidate areas")}
        </Typography>

        <Typography variant="h6">{tr(number(candidateCount, 0))}</Typography>
      </Paper>

      <Paper sx={{ flex: 1, p: 2 }} variant="outlined">
        <Typography color="text.secondary" variant="caption">
          {tr("Included buildings")}
        </Typography>

        <Typography variant="h6">{tr(number(includedBuildings, 0))}</Typography>
      </Paper>

      <Paper sx={{ flex: 1, p: 2 }} variant="outlined">
        <Typography color="text.secondary" variant="caption">
          {tr("Included demand")}
        </Typography>

        <Typography variant="h6">
          {tr(number(demand))} {tr(" MWh/a")}
        </Typography>
      </Paper>

      <Paper sx={{ flex: 1, p: 2 }} variant="outlined">
        <Typography color="text.secondary" variant="caption">
          {tr("Screened network")}
        </Typography>

        <Typography variant="h6">
          {tr(number(networkLength, 0))} {tr(" m")}
        </Typography>
      </Paper>
    </Stack>
  );
}

function CandidateInspector({
  candidate,
}: {
  candidate: PreviewCandidate | null;
}) {
  useLocale();

  if (!candidate) {
    return (
      <Typography color="text.secondary">
        {tr("Select a candidate to inspect its summary.")}
      </Typography>
    );
  }

  return (
    <Stack spacing={1}>
      <Typography variant="h6">
        {tr("Candidate #")}

        {tr(candidate.id)}
      </Typography>

      <Typography color="text.secondary" variant="body2">
        {tr(
          "Preview candidates are read-only. Optimization decisions are made only in a run.",
        )}
      </Typography>

      <Table aria-label={tr(`Candidate ${candidate.id} summary`)} size="small">
        <TableBody>
          <TableRow>
            <TableCell>{tr("Annual heat demand")}</TableCell>

            <TableCell>
              {tr(number(candidate.annual_heat_demand_mwh))} {tr(" MWh/a")}
            </TableCell>
          </TableRow>

          <TableRow>
            <TableCell>{tr("Average LHD")}</TableCell>

            <TableCell>
              {tr(number(candidate.average_linear_heat_density_mwh_per_m_a, 2))}

              {tr(" ")}

              {tr("MWh/(m·a)")}
            </TableCell>
          </TableRow>

          <TableRow>
            <TableCell>{tr("Network length")}</TableCell>

            <TableCell>
              {tr(number(candidate.total_network_length_m, 0))} {tr(" m")}
            </TableCell>
          </TableRow>

          <TableRow>
            <TableCell>{tr("Buildings")}</TableCell>

            <TableCell>{tr(number(candidate.buildings, 0))}</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </Stack>
  );
}

export function CandidatePreview({
  scenarioId,

  previewId,

  onGenerate,

  onExpertSettings,
}: CandidatePreviewProps) {
  useLocale();

  const queryClient = useQueryClient();

  const preview = usePreviewQuery(previewId ?? undefined);

  const candidates = usePreviewCandidatesQuery(previewId ?? undefined);

  const candidateLayer = usePreviewLayerQuery(
    previewId ?? undefined,

    "candidate_areas",
  );

  const lhdLayer = usePreviewLayerQuery(previewId ?? undefined, "lhd");

  const buildingLayer = usePreviewLayerQuery(
    previewId ?? undefined,

    "buildings",
  );

  const screenedLayer = usePreviewLayerQuery(
    previewId ?? undefined,

    "screened_out",
  );

  const [selectedId, setSelectedId] = useState<number | null>(null);

  const generate = useMutation({
    mutationFn: onGenerate,

    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["scenario", scenarioId],
      });
    },
  });

  const cancel = useMutation({
    mutationFn: () => cancelPreview(previewId ?? ""),

    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["preview", previewId] });
    },
  });

  const candidateRecords = useMemo(() => {
    if (candidates.data?.candidates) return candidates.data.candidates;

    return preview.data?.summary?.candidate_summaries ?? [];
  }, [candidates.data?.candidates, preview.data?.summary?.candidate_summaries]);

  const selected =
    candidateRecords.find((candidate) => candidate.id === selectedId) ?? null;

  if (preview.isPending && previewId)
    return <LoadingState label={tr("Loading candidate preview…")} />;

  if (preview.isError && previewId)
    return (
      <FailureState
        error={preview.error}

        onRetry={() => void preview.refetch()}
      />
    );

  const resource = preview.data;

  const status = resource?.status;

  return (
    <Stack spacing={2}>
      <Paper component="section" sx={{ p: 3 }}>
        <Stack
          alignItems={{ sm: "center" }}

          direction={{ sm: "row", xs: "column" }}

          justifyContent="space-between"

          spacing={2}
        >
          <Box>
            <Typography variant="h5">{tr("Candidate preview")}</Typography>

            <Typography color="text.secondary">
              {tr(
                "The guided workflow exposes only the linear heat density threshold. Other model assumptions remain in Expert settings.",
              )}
            </Typography>
          </Box>

          <Stack direction="row" flexWrap="wrap" gap={1}>
            <Button onClick={onExpertSettings} variant="text">
              {tr("Expert settings")}
            </Button>

            <Button
              disabled={generate.isPending}

              onClick={() => generate.mutate()}

              variant="contained"
            >
              {tr(
                generate.isPending
                  ? "Queueing preview…"
                  : resource?.status === "stale"
                    ? "Update preview"
                    : "Generate preview",
              )}
            </Button>

            {resource &&
              (resource.status === "queued" ||
                resource.status === "running") && (
                <Button
                  disabled={cancel.isPending}

                  onClick={() => cancel.mutate()}

                  variant="outlined"
                >
                  {tr("Cancel")}
                </Button>
              )}
          </Stack>
        </Stack>

        {generate.isError && <ApiErrorAlert error={generate.error} />}

        {cancel.isError && <ApiErrorAlert error={cancel.error} />}

        {status && (
          <Stack alignItems="center" direction="row" spacing={1} sx={{ mt: 2 }}>
            <StatusChip status={status} />

            {resource.progress?.stage && (
              <Typography color="text.secondary">
                {tr(resource.progress.stage)}
              </Typography>
            )}

            {resource.progress?.fraction !== null &&
              resource.progress?.fraction !== undefined && (
                <Typography color="text.secondary">
                  {tr(Math.round(resource.progress.fraction * 100))}%
                </Typography>
              )}
          </Stack>
        )}

        {resource?.status === "stale" && (
          <Alert severity="warning" sx={{ mt: 2 }}>
            {tr(resource.stale_reason ?? "The preview must be regenerated.")}
          </Alert>
        )}

        {resource?.status === "failed" && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {tr(resource.failure_summary ?? "Preview generation failed.")}
          </Alert>
        )}

        {resource?.status === "cancelled" && (
          <Alert severity="info" sx={{ mt: 2 }}>
            {tr("Preview generation was cancelled. You can generate it again.")}
          </Alert>
        )}
      </Paper>

      {resource?.status === "ready" && resource.summary && (
        <Summary
          candidateCount={resource.summary.candidate_count}

          demand={resource.summary.included_demand_mwh}

          includedBuildings={resource.summary.included_buildings}

          networkLength={resource.summary.network_length_m}
        />
      )}

      {resource?.status === "ready" && (
        <PreviewMap
          buildings={buildingLayer.data ?? null}

          candidateAreas={candidateLayer.data ?? null}

          lhd={lhdLayer.data ?? null}

          onSelectCandidate={setSelectedId}

          screenedOut={screenedLayer.data ?? null}

          selectedCandidateId={selectedId}
        />
      )}

      {resource?.status === "ready" && (
        <Paper component="section" sx={{ p: 3 }}>
          <Typography gutterBottom variant="h6">
            {tr("Candidate summaries")}
          </Typography>

          <Table aria-label={tr("Candidate preview summaries")} size="small">
            <TableHead>
              <TableRow>
                <TableCell>{tr("Candidate")}</TableCell>

                <TableCell>{tr("Demand (MWh/a)")}</TableCell>

                <TableCell>{tr("Average LHD")}</TableCell>

                <TableCell>{tr("Buildings")}</TableCell>
              </TableRow>
            </TableHead>

            <TableBody>
              {candidateRecords.map((candidate) => (
                <TableRow
                  hover

                  key={candidate.id}

                  onClick={() => setSelectedId(candidate.id)}

                  selected={candidate.id === selectedId}

                  tabIndex={0}

                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ")
                      setSelectedId(candidate.id);
                  }}
                >
                  <TableCell>#{tr(candidate.id)}</TableCell>

                  <TableCell>
                    {tr(number(candidate.annual_heat_demand_mwh))}
                  </TableCell>

                  <TableCell>
                    {tr(
                      number(
                        candidate.average_linear_heat_density_mwh_per_m_a,

                        2,
                      ),
                    )}
                  </TableCell>

                  <TableCell>{tr(number(candidate.buildings, 0))}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <Divider sx={{ my: 2 }} />

          <CandidateInspector candidate={selected} />
        </Paper>
      )}
    </Stack>
  );
}
