import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
  Button,
  Grid,
  Link,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  artifactDownloadUrl,
  getRunLogs,
  resolveApiUrl,
} from "../../api/client";
import {
  useArtifactsQuery,
  useManagedRunQuery,
  useResultSummaryQuery,
} from "../../api/queries";
import type { ArtifactAvailability } from "../../api/results";
import type { RunResource } from "../../api/workflow";
import { bboxAreaKm2, formatAreaKm2, formatCoordinate } from "../area/bbox";
import { ResultWarnings } from "./ResultFeedback";
import { formatFileSize } from "./format";
import {
  ResultPanelError,
  ResultPanelLoading,
  ResultPanelUnavailable,
} from "./ResultPanel";

export function InputsAndDownloads({ runId }: { runId: string }) {
  useLocale();
  const run = useManagedRunQuery(runId);
  const artifacts = useArtifactsQuery(runId);
  const summary = useResultSummaryQuery(runId);
  const runWarnings =
    run.data?.warnings?.map((warning) =>
      typeof warning === "string" ? warning : warning.message,
    ) ?? [];

  return (
    <Stack spacing={2}>
      <Stack spacing={0.5}>
        <Typography component="h2" variant="h5">
          {tr("Inputs & downloads")}
        </Typography>
        <Typography color="text.secondary">
          {tr(
            "The immutable area, configuration, data snapshot, source artifacts, and diagnostics used for this calculation.",
          )}
        </Typography>
      </Stack>
      <ResultWarnings warnings={runWarnings} />
      {run.isPending && (
        <ResultPanelLoading label={tr("Loading run provenance…")} />
      )}
      {run.isError && (
        <ResultPanelError
          error={run.error}
          onRetry={() => void run.refetch()}
          title={tr("Run provenance unavailable")}
        />
      )}
      {run.data && <RunProvenance run={run.data} />}
      {run.data && <DiagnosticsDisclosure run={run.data} />}

      {summary.isError && (
        <ResultPanelError
          error={summary.error}
          onRetry={() => void summary.refetch()}
          title={tr("Result provenance unavailable")}
        />
      )}
      {summary.data?.provenance && (
        <ProvenancePanel provenance={summary.data.provenance} />
      )}

      {artifacts.isPending && (
        <ResultPanelLoading label={tr("Loading artifacts…")} />
      )}
      {artifacts.isError && (
        <ResultPanelError
          error={artifacts.error}
          onRetry={() => void artifacts.refetch()}
          title={tr("Downloads unavailable")}
        />
      )}
      {!artifacts.isPending &&
        !artifacts.isError &&
        !artifacts.data?.items.length && (
          <ResultPanelUnavailable title={tr("No artifacts discovered")} />
        )}
      {!artifacts.isPending &&
      !artifacts.isError &&
      artifacts.data?.items.length ? (
        <ArtifactTable runId={runId} artifacts={artifacts.data.items} />
      ) : null}
    </Stack>
  );
}

function RunProvenance({ run }: { run: RunResource }) {
  useLocale();
  return (
    <Grid container spacing={2}>
      <Grid item md={6} xs={12}>
        <Paper
          component="section"
          elevation={0}
          sx={{ border: 1, borderColor: "divider", height: "100%", p: 2 }}
        >
          <Typography component="h3" gutterBottom variant="h6">
            {tr("Study area")}
          </Typography>
          {run.bbox ? (
            <Stack spacing={0.5}>
              <Typography>
                {tr(formatAreaKm2(bboxAreaKm2(run.bbox)))}{" "}
                {tr(" · west, south, east, north")}
              </Typography>
              <Typography color="text.secondary" variant="body2">
                {tr(run.bbox.map(formatCoordinate).join(", "))}{" "}
                {tr(" · EPSG:4326")}
              </Typography>
            </Stack>
          ) : (
            <Typography color="text.secondary">
              {tr("Extent unavailable.")}
            </Typography>
          )}
        </Paper>
      </Grid>
      <Grid item md={6} xs={12}>
        <Paper
          component="section"
          elevation={0}
          sx={{ border: 1, borderColor: "divider", height: "100%", p: 2 }}
        >
          <Typography component="h3" gutterBottom variant="h6">
            {tr("Calculation provenance")}
          </Typography>
          <Stack spacing={0.5}>
            <ProvenanceRow label={tr("Run")} value={run.id} />
            <ProvenanceRow
              label={tr("Configuration")}
              value={run.configuration_version}
            />
            <ProvenanceRow
              label={tr("Application")}
              value={run.application_version}
            />
            <ProvenanceRow label={tr("Solver")} value={solverLabel(run)} />
            <ProvenanceRow
              label={tr("Scenario revision")}
              value={run.scenario_revision_id}
            />
          </Stack>
        </Paper>
      </Grid>
      <Grid item md={6} xs={12}>
        <SnapshotDisclosure
          label={tr("Configuration snapshot")}
          value={run.configuration_snapshot}
        />
      </Grid>
      <Grid item md={6} xs={12}>
        <SnapshotDisclosure
          label={tr("Data snapshot")}
          value={run.data_snapshot}
        />
      </Grid>
    </Grid>
  );
}

function DiagnosticsDisclosure({ run }: { run: RunResource }) {
  useLocale();
  const [open, setOpen] = useState(false);
  const logs = useQuery({
    queryKey: ["managed-run", run.id, "logs"],
    queryFn: () => getRunLogs(run.id),
    enabled: open,
    retry: false,
  });

  return (
    <Paper
      component="section"
      elevation={0}
      sx={{ border: 1, borderColor: "divider", p: 2 }}
    >
      <details>
        <summary onClick={() => setOpen((value) => !value)}>
          {tr("Diagnostics")}
        </summary>
        {open && (
          <Stack spacing={1} sx={{ mt: 1 }}>
            <Typography color="text.secondary" variant="body2">
              {tr(
                "Technical worker state and logs are kept here so they do not compete with the result outcome.",
              )}
            </Typography>
            <ProvenanceRow label={tr("Status")} value={run.status} />
            <ProvenanceRow label={tr("Stage")} value={run.stage} />
            {run.log_url && (
              <Button
                component={Link}
                href={resolveApiUrl(run.log_url)}
                size="small"
                sx={{ alignSelf: "flex-start" }}
                target="_blank"
                variant="outlined"
              >
                {tr("Download diagnostics")}
              </Button>
            )}
            {run.failure_summary && (
              <Typography color="error.main" variant="body2">
                {tr(run.failure_summary)}
              </Typography>
            )}
            {Object.keys(run.failure_details).length > 0 && (
              <BoxedJson value={redactPaths(run.failure_details)} />
            )}
            {logs.isPending && (
              <ResultPanelLoading label={tr("Loading worker logs…")} />
            )}
            {logs.isError && (
              <ResultPanelError
                error={logs.error}
                onRetry={() => void logs.refetch()}
                title={tr("Worker logs unavailable")}
              />
            )}
            {logs.data &&
              (logs.data.available ? (
                <Typography
                  component="pre"
                  sx={{
                    backgroundColor: "action.hover",
                    maxHeight: 320,
                    overflow: "auto",
                    p: 1,
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {tr(logs.data.content)}
                </Typography>
              ) : (
                <Typography color="text.secondary" variant="body2">
                  {tr("No diagnostic log is available.")}
                </Typography>
              ))}
          </Stack>
        )}
      </details>
    </Paper>
  );
}

function ProvenancePanel({
  provenance,
}: {
  provenance: {
    source_artifacts: string[];
    artifact_checksums: Record<string, string | null>;
    immutable: boolean;
  };
}) {
  useLocale();
  return (
    <Paper
      component="section"
      elevation={0}
      sx={{ border: 1, borderColor: "divider", p: 2 }}
    >
      <Typography component="h3" gutterBottom variant="h6">
        {tr("Result provenance")}
      </Typography>
      <Stack spacing={0.5}>
        <Typography color="text.secondary" variant="body2">
          {tr(
            provenance.immutable
              ? "Immutable completed output."
              : "Output is not marked immutable.",
          )}
        </Typography>
        <Typography variant="body2">
          {tr("Source artifacts: ")}
          {tr(provenance.source_artifacts.join(", ") || "—")}
        </Typography>
        {Object.entries(provenance.artifact_checksums).map(
          ([artifact, checksum]) => (
            <Typography key={artifact} color="text.secondary" variant="caption">
              {tr(artifact)}: {tr(checksum ?? "checksum unavailable")}
            </Typography>
          ),
        )}
      </Stack>
    </Paper>
  );
}

function ArtifactTable({
  artifacts,
  runId,
}: {
  artifacts: ArtifactAvailability[];
  runId: string;
}) {
  useLocale();
  return (
    <Paper
      component="section"
      elevation={0}
      sx={{ border: 1, borderColor: "divider", overflowX: "auto" }}
    >
      <Stack spacing={0.5} sx={{ p: 2, pb: 1 }}>
        <Typography component="h3" variant="h6">
          {tr("Available files")}
        </Typography>
        <Typography color="text.secondary" variant="body2">
          {tr(
            "Missing or invalid optional artifacts remain visible instead of being presented as if they were part of the result.",
          )}
        </Typography>
      </Stack>
      <Table aria-label={tr("Run artifacts")} size="small">
        <TableHead>
          <TableRow>
            <TableCell>{tr("Artifact")}</TableCell>
            <TableCell>{tr("Type")}</TableCell>
            <TableCell>{tr("Status")}</TableCell>
            <TableCell align="right">{tr("Size")}</TableCell>
            <TableCell align="right">{tr("Action")}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {artifacts.map((artifact) => (
            <TableRow key={artifact.id}>
              <TableCell>
                <Typography fontWeight={600}>
                  {artifact.display_name}
                </Typography>
                <Typography color="text.secondary" variant="caption">
                  {tr(artifact.id)}
                </Typography>
              </TableCell>
              <TableCell>{tr(artifact.media_type)}</TableCell>
              <TableCell>
                {tr(artifact.status)}
                {tr(artifact.error ? ` — ${artifact.error}` : "")}
              </TableCell>
              <TableCell align="right">
                {tr(formatFileSize(artifact.byte_size))}
              </TableCell>
              <TableCell align="right">
                {artifact.status === "available" &&
                artifact.available !== false ? (
                  <Button
                    component={Link}
                    download
                    href={artifactDownloadUrl(
                      runId,
                      artifact.id,
                      artifact.download_url,
                    )}
                    size="small"
                    variant="outlined"
                  >
                    {tr("Download")}
                  </Button>
                ) : (
                  "—"
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Paper>
  );
}

function SnapshotDisclosure({
  label,
  value,
}: {
  label: string;
  value: Record<string, unknown>;
}) {
  useLocale();
  return (
    <Paper
      component="section"
      elevation={0}
      sx={{ border: 1, borderColor: "divider", p: 2 }}
    >
      <details>
        <summary>{tr(label)}</summary>
        <Typography color="text.secondary" sx={{ mt: 1 }} variant="body2">
          {tr(
            "Server-owned values recorded for this immutable run. Filesystem paths are omitted from this display.",
          )}
        </Typography>
        <BoxedJson value={redactPaths(value)} />
      </details>
    </Paper>
  );
}

function BoxedJson({ value }: { value: unknown }) {
  useLocale();
  return (
    <Typography
      component="pre"
      sx={{
        backgroundColor: "action.hover",
        fontFamily: "monospace",
        fontSize: "0.75rem",
        maxHeight: 280,
        mt: 1,
        overflow: "auto",
        p: 1,
        whiteSpace: "pre-wrap",
      }}
    >
      {tr(JSON.stringify(value, null, 2))}
    </Typography>
  );
}

function ProvenanceRow({
  label,
  value,
}: {
  label: string;
  value: string | null;
}) {
  useLocale();
  return (
    <Stack direction="row" justifyContent="space-between" spacing={2}>
      <Typography color="text.secondary" variant="body2">
        {tr(label)}
      </Typography>
      <Typography
        sx={{ overflowWrap: "anywhere", textAlign: "right" }}
        variant="body2"
      >
        {tr(value ?? "—")}
      </Typography>
    </Stack>
  );
}

function solverLabel(run: RunResource): string | null {
  if (!run.solver_name && !run.solver_version) return null;
  return [run.solver_name, run.solver_version].filter(Boolean).join(" ");
}

function redactPaths(value: unknown, key = ""): unknown {
  if (/(path|file|directory|root|folder)/i.test(key)) {
    return "[omitted from result view]";
  }
  if (Array.isArray(value)) return value.map((item) => redactPaths(item));
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value).map(([childKey, childValue]) => [
      childKey,
      redactPaths(childValue, childKey),
    ]),
  );
}
