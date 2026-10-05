import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { Stack } from "@mui/material";
import { useParams } from "react-router-dom";

import { featureFlags } from "../../app/featureFlags";
import {
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";
import { useRunQuery } from "../../api/queries";
import { CostsPage } from "./CostsPage";
import { DecentralPage } from "./DecentralPage";
import { DecisionsPage } from "./DecisionsPage";
import { DownloadsPage } from "./DownloadsPage";
import { InputsAndDownloads } from "./InputsAndDownloads";
import { NetworkPage } from "./NetworkPage";
import { NetworkWorkspace } from "./NetworkWorkspace";
import { OverviewPage } from "./OverviewPage";
import { ResultSummary } from "./ResultSummary";
import {
  ConstrainedResultNavigation,
  ResultHeader,
  ResultNavigation,
  type ResultTab,
} from "./ResultShell";
import { SupplyPage } from "./SupplyPage";

const resultTabs: ResultTab[] = [
  "overview",
  "network",
  "decisions",
  "supply",
  "costs",
  "decentral",
  "downloads",
];

function isResultTab(value: string | undefined): value is ResultTab {
  return value !== undefined && resultTabs.includes(value as ResultTab);
}

export function RunResultsPage({ forcedTab }: { forcedTab?: ResultTab } = {}) {
  useLocale();
  const { runId, tab } = useParams();
  const run = useRunQuery(runId);
  const constrained = featureFlags.frontendRedesign;
  const activeTab = forcedTab ?? (isResultTab(tab) ? tab : "overview");

  if (!runId)
    return <FailureState error={new Error("The run identifier is missing.")} />;
  if (run.isPending)
    return <LoadingState label={tr("Loading run manifest…")} />;
  if (run.isError)
    return (
      <FailureState error={run.error} onRetry={() => void run.refetch()} />
    );
  if (!run.data)
    return (
      <FailureState error={new Error("The run manifest is unavailable.")} />
    );

  // `GET /runs/{run_id}` answers with the managed run resource, so the header
  // falls back to the run name to keep the identity on screen.
  return (
    <Stack spacing={3}>
      <ResultHeader
        homeLabel={constrained ? "Run workspace" : "Results portal"}
        homePath={constrained ? `/runs/${encodeURIComponent(runId)}` : "/runs"}
        run={run.data}
      />
      {constrained ? (
        <ConstrainedResultNavigation activeTab={activeTab} runId={runId} />
      ) : (
        <ResultNavigation activeTab={activeTab} runId={runId} />
      )}
      {activeTab === "overview" &&
        (constrained ? (
          <ResultSummary runId={runId} showNavigation={false} />
        ) : (
          <OverviewPage runId={runId} />
        ))}
      {activeTab === "network" &&
        (constrained ? (
          <NetworkWorkspace runId={runId} />
        ) : (
          <NetworkPage runId={runId} />
        ))}
      {activeTab === "decisions" && <DecisionsPage runId={runId} />}
      {activeTab === "supply" && <SupplyPage runId={runId} />}
      {activeTab === "costs" && <CostsPage runId={runId} />}
      {activeTab === "decentral" && <DecentralPage runId={runId} />}
      {activeTab === "downloads" &&
        (constrained ? (
          <InputsAndDownloads runId={runId} />
        ) : (
          <DownloadsPage runId={runId} />
        ))}
    </Stack>
  );
}
