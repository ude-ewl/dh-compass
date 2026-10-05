import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { Alert, Button } from "@mui/material";
import { Link } from "react-router-dom";
import {
  useResultCandidatesQuery,
  useResultIterationsQuery,
  useResultNetworkQuery,
} from "../../api/queries";
import {
  LoadingState,
  FailureState,
} from "../../components/feedback/StateViews";
import { ResultSummary } from "../results/ResultSummary";
import { GridViewer } from "./GridViewer";
import { emptyNetwork, resultSteps } from "./viewerState";

export function CompletedGridViewer({
  runId,
  title,
  subtitle,
  bbox,
}: {
  runId: string;
  title: string;
  subtitle?: string;
  bbox?: [number, number, number, number] | null;
}) {
  useLocale();
  const iterations = useResultIterationsQuery(runId);
  const network = useResultNetworkQuery(runId, [
    "candidate_network",
    "connection_paths",
    "lhd",
  ]);
  const candidates = useResultCandidatesQuery(runId);
  const records = iterations.data?.data ?? [];
  const candidateData = candidates.data?.data ?? [];
  const error = iterations.error ?? network.error ?? candidates.error;
  const loading =
    iterations.isPending || network.isPending || candidates.isPending;
  return (
    <GridViewer
      finalResultsOnly
      title={tr(title)}
      subtitle={tr(subtitle)}
      bbox={bbox}
      steps={resultSteps(records, candidateData)}
      network={network.data?.data?.candidate_network ?? emptyNetwork}
      paths={network.data?.data?.connection_paths}
      lhd={network.data?.data?.lhd}
    >
      {loading && <LoadingState label={tr("Loading grid playback…")} />}
      {error && (
        <FailureState
          error={error}
          onRetry={() => {
            void iterations.refetch();
            void network.refetch();
            void candidates.refetch();
          }}
        />
      )}
      {!loading && !error && records.length === 0 && (
        <Alert severity="info">
          {tr(
            "Decision history is unavailable for this run. Available results are shown below.",
          )}
        </Alert>
      )}
      {[
        ...(iterations.data?.warnings ?? []),
        ...(network.data?.warnings ?? []),
      ].map((warning, index) => (
        <Alert severity="warning" key={index}>
          {tr(warning)}
        </Alert>
      ))}
      <Button component={Link} to={`/runs/${encodeURIComponent(runId)}/files`}>
        {tr("Inputs & downloads")}
      </Button>
      <ResultSummary compact showNavigation={false} runId={runId} />
    </GridViewer>
  );
}
