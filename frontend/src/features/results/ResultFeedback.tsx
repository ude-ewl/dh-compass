import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { Alert, Box, Typography } from "@mui/material";
import type { ReactNode } from "react";

import {
  EmptyState,
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";
import type { ResultEnvelope } from "../../api/results";
import { t } from "../../i18n/messages";

export function ResultLoading({
  label = t("loadingResults"),
}: {
  label?: string;
}) {
  useLocale();
  return <LoadingState label={tr(label)} />;
}

export function ResultUnavailable({
  title = t("resultUnavailableTitle"),
  warnings = [],
  body,
}: {
  title?: string;
  warnings?: string[];
  body?: string;
}) {
  useLocale();
  return (
    <EmptyState
      body={tr(body ?? warnings[0] ?? t("resultUnavailableBody"))}
      title={tr(title)}
    />
  );
}

export function ResultWarnings({ warnings }: { warnings: string[] }) {
  useLocale();
  if (!warnings.length) return null;
  return (
    <Alert severity="warning">
      <Typography fontWeight={600}>{t("resultWarnings")}</Typography>
      <Box component="ul" sx={{ mb: 0, mt: 0.5, pl: 2 }}>
        {warnings.map((warning) => (
          <li key={warning}>{tr(warning)}</li>
        ))}
      </Box>
    </Alert>
  );
}

export function ResultEnvelopeState<T>({
  result,
  children,
}: {
  result:
    | {
        isPending: boolean;
        isError: boolean;
        error: unknown;
        data: ResultEnvelope<T> | undefined;
      }
    | undefined;
  children: (data: T) => ReactNode;
}) {
  useLocale();
  if (!result || result.isPending) return <ResultLoading />;
  if (result.isError) return <FailureState error={result.error} />;
  if (!result.data?.available || result.data.data === null) {
    return <ResultUnavailable warnings={result.data?.warnings} />;
  }
  return (
    <>
      <ResultWarnings warnings={result.data.warnings} />
      {tr(children(result.data.data))}
    </>
  );
}
