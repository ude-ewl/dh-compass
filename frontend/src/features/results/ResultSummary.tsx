import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { useEffect, useState } from "react";
import { useResultSummaryQuery } from "../../api/queries";
import {
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";
import { ResultUnavailable } from "./ResultFeedback";
import { CombinedGridResults } from "./CombinedGridResults";
const INDEX_POLL_MS = 3_000;
const MAX_INDEX_ATTEMPTS = 20;

/**
 * Final combined-grid results shared by the completed viewer and summary route.
 */
export function ResultSummary({
  runId,
}: {
  runId: string;
  showNavigation?: boolean;
  compact?: boolean;
}) {
  useLocale();
  const summary = useResultSummaryQuery(runId);
  const [attempts, setAttempts] = useState(0);
  const refetchSummary = summary.refetch;
  const indexed = Boolean(summary.data?.available && summary.data.data);
  const indexing = !summary.isPending && !summary.isError && !indexed;

  useEffect(() => {
    setAttempts(0);
  }, [runId]);

  // Reporting can finish slightly before the output folder is indexed. Keep
  // checking for a bounded time so completion does not require a reload.
  useEffect(() => {
    if (!indexing || attempts >= MAX_INDEX_ATTEMPTS) return undefined;
    const timer = setTimeout(() => {
      setAttempts((value) => value + 1);
      void refetchSummary();
    }, INDEX_POLL_MS);
    return () => clearTimeout(timer);
  }, [attempts, indexing, refetchSummary]);

  if (summary.isPending) {
    return <LoadingState label={tr("Loading the result summary…")} />;
  }
  if (summary.isError) {
    return (
      <FailureState
        error={summary.error}
        onRetry={() => void summary.refetch()}
      />
    );
  }
  if (!indexed) {
    return (
      <ResultUnavailable
        body={tr(
          "Reporting has finished and the result files are still being indexed. This page checks again automatically.",
        )}
        title={tr("Result is being indexed")}
        warnings={summary.data?.warnings}
      />
    );
  }

  return <CombinedGridResults runId={runId} summary={summary.data!.data!} />;
}
