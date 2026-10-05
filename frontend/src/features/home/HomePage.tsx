import { useLocale } from "../../i18n/locale";
import { Button, Paper, Stack, Typography } from "@mui/material";
import { Link } from "react-router-dom";

import { useHealthQuery } from "../../api/queries";
import { t } from "../../i18n/messages";
import {
  EmptyState,
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";

export function HomePage() {
  useLocale();
  const health = useHealthQuery();

  return (
    <Stack spacing={3}>
      <header>
        <Typography gutterBottom variant="overline">
          {t("appName")}
        </Typography>
        <Typography gutterBottom variant="h3">
          {t("welcomeHeading")}
        </Typography>
        <Typography color="text.secondary" maxWidth={720}>
          {t("welcomeBody")}
        </Typography>
      </header>

      <Paper
        component="section"
        elevation={0}
        sx={{ border: 1, borderColor: "divider", p: 3 }}
      >
        {health.isPending && <LoadingState label={t("connectingApi")} />}
        {health.isError && (
          <FailureState
            error={health.error}
            onRetry={() => void health.refetch()}
          />
        )}
        {health.isSuccess && (
          <EmptyState
            action={
              <Button component={Link} to="/projects" variant="contained">
                {t("createProject")}
              </Button>
            }
            body={t("workspaceReadyBody")}
            title={t("workspaceReadyTitle")}
          />
        )}
      </Paper>
    </Stack>
  );
}
