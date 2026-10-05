import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
  Box,
  Button,
  FormControlLabel,
  Paper,
  Stack,
  Switch,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";

import {
  useResultCandidateQuery,
  useResultCandidatesQuery,
  useResultNetworkQuery,
} from "../../api/queries";
import type { NetworkResult } from "../../api/results";
import { PanelErrorBoundary } from "../../components/feedback/PanelErrorBoundary";
import { ResultUnavailable, ResultWarnings } from "./ResultFeedback";
import { CandidateInspector } from "./CandidateInspector";
import { CandidateTable } from "./CandidateTable";
import { ResultMap } from "./ResultMap";
import {
  ResultPanelError,
  ResultPanelLoading,
  ResultPanelUnavailable,
} from "./ResultPanel";
import { useResultSelection } from "./selection";

interface LayerPreferences {
  finalNetwork: boolean;
  candidates: boolean;
  lhd: boolean;
  paths: boolean;
  buildings: boolean;
  screenedOut: boolean;
}

const defaultLayers: LayerPreferences = {
  finalNetwork: true,
  candidates: true,
  lhd: false,
  paths: true,
  buildings: true,
  screenedOut: false,
};

function loadLayerPreferences(runId: string): LayerPreferences {
  if (typeof window === "undefined") return defaultLayers;
  try {
    const stored = window.localStorage.getItem(`dh-compass:layers:${runId}`);
    if (!stored) return defaultLayers;
    const parsed = JSON.parse(stored) as Partial<LayerPreferences>;
    return { ...defaultLayers, ...parsed };
  } catch {
    return defaultLayers;
  }
}

function saveLayerPreferences(runId: string, value: LayerPreferences): void {
  try {
    window.localStorage.setItem(
      `dh-compass:layers:${runId}`,
      JSON.stringify(value),
    );
  } catch {
    // Storage-disabled environments should not break result inspection.
  }
}

export function NetworkWorkspace({ runId }: { runId: string }) {
  useLocale();
  const [layers, setLayers] = useState<LayerPreferences>(() =>
    loadLayerPreferences(runId),
  );
  const [fitRequest, setFitRequest] = useState(0);
  const network = useResultNetworkQuery(runId, [
    "final_network",
    "candidate_network",
    "connection_paths",
    ...(layers.lhd ? ["lhd"] : []),
  ]);
  const candidates = useResultCandidatesQuery(runId);
  const { candidateId: selectedCandidateId, selectCandidate } =
    useResultSelection();
  const candidateDetail = useResultCandidateQuery(runId, selectedCandidateId);

  useEffect(() => {
    setLayers(loadLayerPreferences(runId));
  }, [runId]);

  const networkData =
    network.data?.available && network.data.data ? network.data.data : null;
  const candidateData =
    candidates.data?.available && candidates.data.data
      ? candidates.data.data
      : [];
  const selectedCandidate =
    candidateDetail.data?.available && candidateDetail.data.data
      ? candidateDetail.data.data
      : (candidateData.find((item) => item.id === selectedCandidateId) ?? null);

  const setLayer = (key: keyof LayerPreferences, value: boolean) => {
    setLayers((current) => {
      const next = { ...current, [key]: value };
      saveLayerPreferences(runId, next);
      return next;
    });
  };

  return (
    <Stack spacing={2}>
      <Stack spacing={0.5}>
        <Typography component="h2" variant="h5">
          {tr("Network details")}
        </Typography>
        <Typography color="text.secondary">
          {tr(
            "Select a candidate on the map or in the table to see the evidence for its connected or rejected decision. The map, table, and inspector share one selection.",
          )}
        </Typography>
      </Stack>
      <ResultWarnings
        warnings={uniqueWarnings(
          network.data?.warnings,
          candidates.data?.warnings,
          candidateDetail.data?.warnings,
        )}
      />
      {networkData && (
        <NetworkLayerControls
          layers={layers}
          onFit={() => setFitRequest((value) => value + 1)}
          onSetLayer={setLayer}
          availability={networkData.availability}
        />
      )}
      <Paper
        aria-label={tr("Network decision workspace")}
        component="section"
        elevation={0}
        sx={{ border: 1, borderColor: "divider", p: { md: 1, xs: 0 } }}
      >
        <Box
          sx={{
            display: "grid",
            gap: 1,
            gridTemplateColumns: {
              md: "minmax(0, 2fr) minmax(300px, 1fr)",
              xs: "1fr",
            },
          }}
        >
          <Box sx={{ minWidth: 0 }}>
            {network.isPending && (
              <ResultPanelLoading label={tr("Loading network map…")} />
            )}
            {network.isError && (
              <ResultPanelError
                error={network.error}
                onRetry={() => void network.refetch()}
                title={tr("Network map unavailable")}
              />
            )}
            {!network.isPending && !network.isError && !networkData && (
              <ResultPanelUnavailable
                title={tr("Network map unavailable")}
                warnings={network.data?.warnings}
              />
            )}
            <PanelErrorBoundary
              resetKey={`${runId}:map:${network.data?.content_hash ?? "empty"}`}
              title={tr("Network and candidate map")}
            >
              {networkData && (
                <ResultMap
                  buildingLocations={networkData.buildings}
                  candidateNetwork={networkData.candidate_network}
                  connectionPaths={networkData.connection_paths}
                  finalNetwork={networkData.final_network}
                  fitRequest={fitRequest}
                  lhd={networkData.lhd}
                  onSelectCandidate={selectCandidate}
                  screenedOut={networkData.screened_out}
                  selectedCandidateId={selectedCandidateId}
                  showBuildings={layers.buildings}
                  showCandidates={layers.candidates}
                  showFinalNetwork={layers.finalNetwork}
                  showLhd={layers.lhd}
                  showPaths={layers.paths}
                  showScreenedOut={layers.screenedOut}
                  title={tr("Network and candidate map")}
                />
              )}
            </PanelErrorBoundary>
          </Box>
          <Box sx={{ minWidth: 0, p: { md: 1, xs: 1 } }}>
            {candidates.isPending && (
              <ResultPanelLoading label={tr("Loading candidate evidence…")} />
            )}
            {candidates.isError && (
              <ResultPanelError
                error={candidates.error}
                onRetry={() => void candidates.refetch()}
                title={tr("Candidate evidence unavailable")}
              />
            )}
            {!candidates.isPending &&
              !candidates.isError &&
              !candidates.data?.available && (
                <ResultPanelUnavailable
                  title={tr("Candidate evidence unavailable")}
                  warnings={candidates.data?.warnings}
                />
              )}
            {!candidates.isPending &&
              !candidates.isError &&
              candidates.data?.available && (
                <PanelErrorBoundary
                  resetKey={`${runId}:inspector:${selectedCandidateId ?? "none"}`}
                  title={tr("Candidate inspector")}
                >
                  <CandidateInspector candidate={selectedCandidate} />
                </PanelErrorBoundary>
              )}
          </Box>
        </Box>
      </Paper>
      <Box>
        {candidates.isPending && (
          <ResultPanelLoading label={tr("Loading candidate table…")} />
        )}
        {candidates.isError && (
          <ResultPanelError
            error={candidates.error}
            onRetry={() => void candidates.refetch()}
            title={tr("Candidate table unavailable")}
          />
        )}
        {!candidates.isPending &&
          !candidates.isError &&
          candidates.data?.available &&
          candidateData.length > 0 && (
            <PanelErrorBoundary
              resetKey={`${runId}:table:${candidateData.length}`}
              title={tr("Candidate table")}
            >
              <CandidateTable
                candidates={candidateData}
                onSelect={selectCandidate}
                selectedCandidateId={selectedCandidateId}
              />
            </PanelErrorBoundary>
          )}
        {!candidates.isPending &&
          !candidates.isError &&
          (!candidates.data?.available || candidateData.length === 0) && (
            <ResultUnavailable
              body={tr(candidates.data?.warnings?.[0])}
              title={tr("Candidate table unavailable")}
            />
          )}
      </Box>
    </Stack>
  );
}

function NetworkLayerControls({
  availability,
  layers,
  onFit,
  onSetLayer,
}: {
  availability: NetworkResult["availability"];
  layers: LayerPreferences;
  onFit: () => void;
  onSetLayer: (key: keyof LayerPreferences, value: boolean) => void;
}) {
  useLocale();
  return (
    <Paper
      aria-label={tr("Network layer controls")}
      component="section"
      elevation={0}
      sx={{ border: 1, borderColor: "divider", p: 1.5 }}
    >
      <Stack
        alignItems={{ md: "center", xs: "flex-start" }}
        direction={{ md: "row", xs: "column" }}
        flexWrap="wrap"
        gap={1}
      >
        <Typography component="h3" sx={{ mr: 1 }} variant="subtitle2">
          {tr("Layers")}
        </Typography>
        <FormControlLabel
          control={
            <Switch
              checked={layers.finalNetwork}
              onChange={(event) =>
                onSetLayer("finalNetwork", event.target.checked)
              }
            />
          }
          label={tr("Final network")}
        />
        <FormControlLabel
          control={
            <Switch
              checked={layers.candidates}
              onChange={(event) =>
                onSetLayer("candidates", event.target.checked)
              }
            />
          }
          label={tr("Candidate areas")}
        />
        <FormControlLabel
          control={
            <Switch
              checked={layers.lhd}
              onChange={(event) => onSetLayer("lhd", event.target.checked)}
            />
          }
          label={tr("Linear heat density")}
        />
        <FormControlLabel
          control={
            <Switch
              checked={layers.paths}
              onChange={(event) => onSetLayer("paths", event.target.checked)}
            />
          }
          label={tr("Connection paths")}
        />
        <FormControlLabel
          control={
            <Switch
              checked={layers.buildings}
              disabled={!availability.buildings}
              onChange={(event) =>
                onSetLayer("buildings", event.target.checked)
              }
            />
          }
          label={tr("Buildings")}
        />
        <FormControlLabel
          control={
            <Switch
              checked={layers.screenedOut}
              disabled={!availability.screened_out}
              onChange={(event) =>
                onSetLayer("screenedOut", event.target.checked)
              }
            />
          }
          label={tr("Screened-out edges")}
        />
        <Button
          onClick={onFit}
          size="small"
          sx={{ ml: { md: "auto" } }}
          variant="outlined"
        >
          {tr("Fit all visible layers")}
        </Button>
      </Stack>
      <Stack
        aria-label={tr("Network layer legend")}
        direction="row"
        flexWrap="wrap"
        gap={2}
        sx={{ mt: 1, pl: 1 }}
      >
        <Legend color="#17324d" label={tr("Final network")} />
        <Legend color="#2f855a" label={tr("Connected candidate")} />
        <Legend color="#b42318" label={tr("Rejected candidate")} />
        <Legend color="#d94801" label={tr("Linear heat density")} />
        <Legend color="#7c3aed" label={tr("Connection path")} />
      </Stack>
    </Paper>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  useLocale();
  return (
    <Stack alignItems="center" direction="row" role="listitem" spacing={0.5}>
      <Box
        aria-hidden="true"
        sx={{ backgroundColor: color, borderRadius: 1, height: 3, width: 20 }}
      />
      <Typography variant="caption">{tr(label)}</Typography>
    </Stack>
  );
}

function uniqueWarnings(...groups: (string[] | undefined)[]): string[] {
  return [...new Set(groups.flatMap((group) => group ?? []))];
}
