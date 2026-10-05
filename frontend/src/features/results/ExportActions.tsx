import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { Alert, Button, Link, Stack, Typography } from "@mui/material";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import {
  createRunBundle,
  createRunReport,
  resolveApiUrl,
  runCsvUrl,
} from "../../api/client";
import { useExportJobQuery } from "../../api/queries";
import { t } from "../../i18n/messages";

export function ExportActions({ runId }: { runId: string }) {
  useLocale();
  const [reportId, setReportId] = useState<string>();
  const [bundleId, setBundleId] = useState<string>();
  const report = useExportJobQuery(reportId);
  const bundle = useExportJobQuery(bundleId);
  const reportMutation = useMutation({
    mutationFn: () => createRunReport(runId),
    onSuccess: (job) => setReportId(job.id),
  });
  const bundleMutation = useMutation({
    mutationFn: () => createRunBundle(runId),
    onSuccess: (job) => setBundleId(job.id),
  });

  return (
    <Stack spacing={2}>
      <Typography component="h3" variant="h6">
        {t("exportResults")}
      </Typography>
      <Stack
        direction={{ sm: "row", xs: "column" }}
        spacing={1}
        useFlexGap
        flexWrap="wrap"
      >
        <Button
          disabled={reportMutation.isPending}
          onClick={() => reportMutation.mutate()}
          variant="outlined"
        >
          {tr(
            reportMutation.isPending
              ? t("generatingReport")
              : t("generateReport"),
          )}
        </Button>
        <Button
          disabled={bundleMutation.isPending}
          onClick={() => bundleMutation.mutate()}
          variant="outlined"
        >
          {tr(
            bundleMutation.isPending
              ? t("generatingBundle")
              : t("downloadBundle"),
          )}
        </Button>
        <Button
          component={Link}
          download
          href={runCsvUrl(runId, "candidates")}
          variant="outlined"
        >
          {t("downloadCandidatesCsv")}
        </Button>
        <Button
          component={Link}
          download
          href={runCsvUrl(runId, "costs")}
          variant="outlined"
        >
          {t("downloadCostsCsv")}
        </Button>
        <Button
          component={Link}
          download
          href={runCsvUrl(runId, "supply")}
          variant="outlined"
        >
          {t("downloadSupplyCsv")}
        </Button>
        <Button
          component={Link}
          download
          href={runCsvUrl(runId, "iterations")}
          variant="outlined"
        >
          {t("downloadIterationsCsv")}
        </Button>
        <Button
          component={Link}
          download
          href={runCsvUrl(runId, "decentral")}
          variant="outlined"
        >
          {t("downloadDecentralCsv")}
        </Button>
      </Stack>
      {(reportMutation.isError || bundleMutation.isError) && (
        <Alert severity="error">{t("exportFailed")}</Alert>
      )}
      {report.data && (
        <ExportStatus label={t("printableReport")} job={report.data} />
      )}
      {bundle.data && (
        <ExportStatus label={t("reproducibilityBundle")} job={bundle.data} />
      )}
    </Stack>
  );
}

function ExportStatus({
  label,
  job,
}: {
  label: string;
  job: { status: string; download_url: string | null; error: string | null };
}) {
  useLocale();
  if (job.status === "failed") {
    return (
      <Alert severity="error">
        {tr(label)}: {tr(job.error ?? t("exportFailed"))}
      </Alert>
    );
  }
  if (job.status !== "available" || !job.download_url) {
    return (
      <Typography color="text.secondary">
        {tr(label)}: {t("exportInProgress")}
      </Typography>
    );
  }
  return (
    <Button
      component={Link}
      download
      href={resolveApiUrl(job.download_url)}
      variant="contained"
    >
      {tr(label)}: {t("downloadReady")}
    </Button>
  );
}
