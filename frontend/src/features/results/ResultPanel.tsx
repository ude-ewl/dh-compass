import { tr } from "../../i18n/translate";

import { useLocale } from "../../i18n/locale";

import { Alert, Box, Button, Stack, Typography } from "@mui/material";

import type { ReactNode } from "react";

import { EmptyState, LoadingState } from "../../components/feedback/StateViews";

export function ResultPanel({
  children,

  label,
}: {
  children: ReactNode;

  label: string;
}) {
  useLocale();

  return (
    <Box aria-label={tr(label)} component="section" sx={{ minWidth: 0 }}>
      {tr(children)}
    </Box>
  );
}

export function ResultPanelLoading({ label }: { label: string }) {
  useLocale();

  return (
    <ResultPanel label={tr(label)}>
      <LoadingState label={tr(label)} />
    </ResultPanel>
  );
}

export function ResultPanelError({
  error,

  onRetry,

  title,
}: {
  error: unknown;

  onRetry?: () => void;

  title: string;
}) {
  useLocale();

  const message =
    error instanceof Error
      ? error.message
      : "The result panel could not be loaded.";

  const requestId =
    typeof error === "object" && error !== null && "payload" in error
      ? ((error as { payload?: { request_id?: string } }).payload?.request_id ??
        undefined)
      : undefined;

  return (
    <ResultPanel label={tr(title)}>
      <Alert severity="error">
        <Stack spacing={0.75}>
          <Typography fontWeight={600}>{tr(title)}</Typography>

          <Typography variant="body2">{tr(message)}</Typography>

          {requestId && (
            <Typography variant="caption">
              {tr("Request ID: ")}

              {tr(requestId)}
            </Typography>
          )}

          {onRetry && (
            <Button
              onClick={onRetry}

              size="small"

              sx={{ alignSelf: "flex-start" }}

              variant="outlined"
            >
              {tr("Retry this panel")}
            </Button>
          )}
        </Stack>
      </Alert>
    </ResultPanel>
  );
}

export function ResultPanelUnavailable({
  body,

  title,

  warnings,
}: {
  body?: string;

  title: string;

  warnings?: string[];
}) {
  useLocale();

  return (
    <ResultPanel label={tr(title)}>
      <EmptyState body={tr(body ?? warnings?.[0])} title={tr(title)} />
    </ResultPanel>
  );
}
