import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { Alert, Button, Typography } from "@mui/material";

import { ApiClientError } from "../../api/client";
import { t } from "../../i18n/messages";

export function ApiErrorAlert({
  error,
  onRetry,
  retryLabel = t("retry"),
}: {
  error: unknown;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  useLocale();
  const message = error instanceof Error ? error.message : t("requestFailed");
  const fieldErrors =
    error instanceof ApiClientError ? (error.payload.field_errors ?? []) : [];
  const requestId =
    error instanceof ApiClientError && error.payload.request_id !== "unknown"
      ? error.payload.request_id
      : null;

  return (
    <Alert severity="error">
      <Typography component="div" variant="body2">
        {tr(message)}
      </Typography>
      {fieldErrors.length > 0 && (
        <ul>
          {fieldErrors.map((fieldError) => (
            <li key={`${fieldError.path}:${fieldError.message}`}>
              <strong>{tr(fieldError.path)}</strong>: {tr(fieldError.message)}
            </li>
          ))}
        </ul>
      )}
      {requestId && (
        <Typography color="text.secondary" variant="caption">
          {t("requestId")}: {tr(requestId)}
        </Typography>
      )}
      {onRetry && (
        <Button
          onClick={onRetry}
          size="small"
          sx={{ mt: 0.5 }}
          variant="outlined"
        >
          {tr(retryLabel)}
        </Button>
      )}
    </Alert>
  );
}
