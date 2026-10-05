import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Typography,
} from "@mui/material";
import type { ReactNode } from "react";

import { messages, t } from "../../i18n/messages";

export function LoadingState({ label = t("loading") }: { label?: string }) {
  useLocale();
  return (
    <Box
      alignItems="center"
      display="flex"
      gap={1}
      role="status"
      sx={{ py: 3 }}
    >
      <CircularProgress aria-label={tr(label)} size={20} />
      <Typography>{tr(label)}</Typography>
    </Box>
  );
}

export function EmptyState({
  title = t("emptyTitle"),
  body = t("emptyBody"),
  action,
}: {
  title?: string;
  body?: string;
  action?: ReactNode;
}) {
  useLocale();
  return (
    <Box aria-label={tr(title)} sx={{ py: 6, textAlign: "center" }}>
      <Typography gutterBottom variant="h5">
        {tr(title)}
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        {tr(body)}
      </Typography>
      {tr(action)}
    </Box>
  );
}

export function WarningState({
  title = t("warningTitle"),
  children,
}: {
  title?: string;
  children: ReactNode;
}) {
  useLocale();
  return (
    <Alert severity="warning" sx={{ my: 2 }}>
      <strong>{tr(title)}</strong>
      <Box component="span" sx={{ display: "block" }}>
        {tr(children)}
      </Box>
    </Alert>
  );
}

export function FailureState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  useLocale();
  const message = error instanceof Error ? error.message : t("requestFailed");
  const requestId =
    typeof error === "object" && error !== null && "payload" in error
      ? ((error as { payload?: { request_id?: string } }).payload?.request_id ??
        undefined)
      : undefined;

  return (
    <Alert severity="error" sx={{ my: 2 }}>
      <Typography fontWeight={600}>{tr(message)}</Typography>
      {requestId && (
        <Typography variant="body2">
          {tr(messages.requestId)}: {tr(requestId)}
        </Typography>
      )}
      {onRetry && (
        <Button
          onClick={onRetry}
          size="small"
          sx={{ mt: 1 }}
          variant="outlined"
        >
          {t("retry")}
        </Button>
      )}
    </Alert>
  );
}
