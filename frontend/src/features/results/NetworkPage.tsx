import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
  Box,
  Button,
  FormControlLabel,
  Grid,
  Paper,
  Stack,
  Switch,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";

import {
  useResultCandidatesQuery,
  useResultNetworkQuery,
} from "../../api/queries";
import {
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";
import { ResultUnavailable, ResultWarnings } from "./ResultFeedback";
import { CandidateInspector, CandidateTable } from "./CandidateTable";
import { ResultMap } from "./ResultMap";
import { useResultSelection } from "./selection";

type LayerPreferences = {
  finalNetwork: boolean;
  candidates: boolean;
  lhd: boolean;
  paths: boolean;
  buildings: boolean;
  screenedOut: boolean;
};

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
    // Private browsing/storage-disabled environments should not break maps.
  }
}

export function NetworkPage({ runId }: { runId: string }) {
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

  useEffect(() => {
    setLayers(loadLayerPreferences(runId));
  }, [runId]);

  if (network.isPending || candidates.isPending)
    return <LoadingState label={tr("Loading network layers…")} />;
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
  if (!network.data?.available || !network.data.data) {
    return <ResultUnavailable warnings={network.data?.warnings} />;
  }

  const candidateData =
    candidates.data?.available && candidates.data.data
      ? candidates.data.data
      : [];
  const selectedCandidate =
    candidateData.find((item) => item.id === selectedCandidateId) ?? null;

  const setLayer = (key: keyof LayerPreferences, value: boolean) => {
    setLayers((current) => {
      const next = { ...current, [key]: value };
      saveLayerPreferences(runId, next);
      return next;
    });
  };

  return (
    <Stack spacing={2}>
      <Typography component="h2" variant="h5">
        {tr("Network layers")}
      </Typography>
      <ResultWarnings
        warnings={[
          ...(network.data.warnings ?? []),
          ...(candidates.data?.warnings ?? []),
        ]}
      />
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
                  setLayer("finalNetwork", event.target.checked)
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
                  setLayer("candidates", event.target.checked)
                }
              />
            }
            label={tr("Candidate areas")}
          />
          <FormControlLabel
            control={
              <Switch
                checked={layers.lhd}
                onChange={(event) => setLayer("lhd", event.target.checked)}
              />
            }
            label={tr("Linear heat density")}
          />
          <FormControlLabel
            control={
              <Switch
                checked={layers.paths}
                onChange={(event) => setLayer("paths", event.target.checked)}
              />
            }
            label={tr("Connection paths")}
          />
          <FormControlLabel
            control={
              <Switch
                checked={layers.buildings}
                disabled={!network.data.data.availability.buildings}
                onChange={(event) =>
                  setLayer("buildings", event.target.checked)
                }
              />
            }
            label={tr("Buildings")}
          />
          <FormControlLabel
            control={
              <Switch
                checked={layers.screenedOut}
                disabled={!network.data.data.availability.screened_out}
                onChange={(event) =>
                  setLayer("screenedOut", event.target.checked)
                }
              />
            }
            label={tr("Screened-out edges")}
          />
          <Button
            onClick={() => setFitRequest((value) => value + 1)}
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
          <Legend color="#2f855a" label={tr("Connected")} />
          <Legend color="#b42318" label={tr("Rejected")} />
          <Legend color="#d94801" label={tr("LHD")} />
          <Legend color="#7c3aed" label={tr("Connection path")} />
        </Stack>
      </Paper>
      <Grid container spacing={2}>
        <Grid item md={8} xs={12}>
          <ResultMap
            candidateNetwork={network.data.data.candidate_network}
            connectionPaths={network.data.data.connection_paths}
            finalNetwork={network.data.data.final_network}
            fitRequest={fitRequest}
            lhd={network.data.data.lhd}
            onSelectCandidate={selectCandidate}
            screenedOut={network.data.data.screened_out}
            selectedCandidateId={selectedCandidateId}
            showBuildings={layers.buildings}
            showCandidates={layers.candidates}
            showFinalNetwork={layers.finalNetwork}
            showLhd={layers.lhd}
            showPaths={layers.paths}
            showScreenedOut={layers.screenedOut}
            title={tr("Network layers map")}
          />
        </Grid>
        <Grid item md={4} xs={12}>
          <CandidateInspector candidate={selectedCandidate} />
        </Grid>
      </Grid>
      {candidateData.length ? (
        <CandidateTable
          candidates={candidateData}
          onSelect={selectCandidate}
          selectedCandidateId={selectedCandidateId}
        />
      ) : (
        <ResultUnavailable title={tr("Candidate layer unavailable")} />
      )}
      <Box component="div" sx={{ m: 0 }}>
        <Typography color="text.secondary" variant="body2">
          {tr(
            "Layer visibility is remembered for this run on this browser. Map colors are accompanied by labels and an accessible candidate table.",
          )}
        </Typography>
      </Box>
    </Stack>
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
