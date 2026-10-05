import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { Button, Stack, Typography } from "@mui/material";
import { isRouteErrorResponse, Link, useRouteError } from "react-router-dom";

import { t } from "../../i18n/messages";

export function RouteErrorBoundary() {
  useLocale();
  const error = useRouteError();
  const detail = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : t("unknownRouteError");

  return (
    <Stack
      alignItems="center"
      role="alert"
      spacing={2}
      sx={{ m: "auto", maxWidth: 640, p: 4 }}
    >
      <Typography variant="h4">{t("routeFailureTitle")}</Typography>
      <Typography color="text.secondary">{t("routeFailureBody")}</Typography>
      <Typography color="text.secondary" variant="body2">
        {tr(detail)}
      </Typography>
      <Button component={Link} to="/" variant="contained">
        {t("returnToWorkspace")}
      </Button>
    </Stack>
  );
}
