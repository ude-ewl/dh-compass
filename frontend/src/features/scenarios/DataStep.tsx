import { tr } from "../../i18n/translate";

import { useLocale } from "../../i18n/locale";

import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Button,
  Chip,
  Divider,
  Paper,
  Stack,
  Typography,
} from "@mui/material";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useState } from "react";

import { refreshDataset, validateDatasets } from "../../api/client";

import type { DatasetDescriptor } from "../../api/workflow";

import { useDatasetLayerQuery, useDatasetsQuery } from "../../api/queries";

import { ApiErrorAlert } from "../../components/feedback/ApiErrorAlert";

import {
  EmptyState,
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";

import { PreviewMap } from "./PreviewMap";

const resourceDatasetIds = new Set([
  "industrial_excess_heat",

  "biomass",

  "waste_to_energy",

  "geothermal",

  "river_heat_pump",

  "wwtp_heat_pump",
]);

function isResourceDataset(dataset: DatasetDescriptor): boolean {
  return resourceDatasetIds.has(dataset.id);
}

function hasNonBlockingNotice(dataset: DatasetDescriptor): boolean {
  return dataset.status === "ready" && dataset.issues.length > 0;
}

function statusColor(
  dataset: DatasetDescriptor,
): "success" | "warning" | "error" | "default" {
  if (dataset.status === "ready")
    return hasNonBlockingNotice(dataset) ? "warning" : "success";

  if (dataset.status === "missing" || dataset.status === "invalid")
    return "error";

  if (dataset.status === "stale" || dataset.status === "downloading")
    return "warning";

  return "default";
}

function statusLabel(dataset: DatasetDescriptor): string {
  if (hasNonBlockingNotice(dataset)) return "coverage notice";

  return dataset.status;
}

function requirementLabel(dataset: DatasetDescriptor): string {
  if (isResourceDataset(dataset))
    return dataset.required ? "Enabled resource" : "Optional resource";

  return dataset.required ? "Required input" : "Optional input";
}

function DatasetMapPreview({
  scenarioId,

  dataset,
}: {
  scenarioId: string;

  dataset: DatasetDescriptor;
}) {
  useLocale();

  const [open, setOpen] = useState(false);

  const layer = useDatasetLayerQuery(scenarioId, open ? dataset.id : null);

  if (!open) {
    if (dataset.status !== "ready") {
      return (
        <Typography color="text.secondary" variant="caption">
          {tr("Map preview is available after this dataset is ready.")}
        </Typography>
      );
    }

    return (
      <Button onClick={() => setOpen(true)} size="small">
        {tr("Map preview")}
      </Button>
    );
  }

  if (layer.isPending)
    return <LoadingState label={tr("Loading map preview…")} />;

  if (layer.isError)
    return (
      <Stack spacing={1}>
        <ApiErrorAlert error={layer.error} />

        <Button onClick={() => setOpen(false)} size="small">
          {tr("Hide map preview")}
        </Button>
      </Stack>
    );

  return (
    <Stack spacing={1}>
      <Typography variant="body2">
        {tr("Map preview: ")}
        {tr(layer.data.geojson.features.length)} {tr(" features")}
        {tr(layer.data.truncated ? " (first 5\u202f000 shown)" : "")}.
      </Typography>

      <PreviewMap candidateAreas={layer.data.geojson} />

      <Paper
        aria-label={tr(`${dataset.label} metadata inspector`)}

        sx={{ maxHeight: 160, overflow: "auto", p: 1 }}

        variant="outlined"
      >
        <Typography
          component="pre"

          sx={{ m: 0, whiteSpace: "pre-wrap" }}

          variant="caption"
        >
          {tr(JSON.stringify(layer.data.geojson.features.slice(0, 2), null, 2))}
        </Typography>
      </Paper>

      <Button onClick={() => setOpen(false)} size="small">
        {tr("Hide map preview")}
      </Button>
    </Stack>
  );
}

function DatasetCard({
  scenarioId,

  dataset,
}: {
  scenarioId: string;

  dataset: DatasetDescriptor;
}) {
  useLocale();

  const queryClient = useQueryClient();

  const refresh = useMutation({
    mutationFn: () => refreshDataset(scenarioId, dataset.id),

    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["scenario", scenarioId, "datasets"],
      });
    },
  });

  return (
    <Paper component="article" sx={{ p: 2 }} variant="outlined">
      <Stack spacing={1}>
        <Stack
          alignItems="center"

          direction="row"

          justifyContent="space-between"

          spacing={1}
        >
          <BoxTitle dataset={dataset} />

          <Chip
            color={statusColor(dataset)}

            label={tr(statusLabel(dataset))}

            size="small"
          />
        </Stack>

        <Typography color="text.secondary" variant="body2">
          {dataset.description}
        </Typography>

        <Typography variant="body2">
          {tr(dataset.path_display ?? "Managed provider")}

          {tr(dataset.layer ? ` · layer ${dataset.layer}` : "")}
        </Typography>

        {dataset.crs && (
          <Typography color="text.secondary" variant="caption">
            {tr("CRS: ")}

            {tr(dataset.crs)}
          </Typography>
        )}

        {dataset.issues.map((issue) => (
          <Alert
            key={`${dataset.id}-${issue.code}-${issue.message}`}

            severity={
              issue.severity === "error"
                ? "error"
                : issue.severity === "warning"
                  ? "warning"
                  : "info"
            }
          >
            <strong>{tr(issue.code)}</strong>: {tr(issue.message)}
            {issue.remediation && (
              <Typography variant="caption">
                {" "}
                {tr(issue.remediation)}
              </Typography>
            )}
          </Alert>
        ))}

        {refresh.isError && <ApiErrorAlert error={refresh.error} />}

        <Stack direction="row" flexWrap="wrap" gap={1}>
          <DatasetMapPreview dataset={dataset} scenarioId={scenarioId} />

          {dataset.actions

            .filter((action) => action.action === "refresh" && action.allowed)

            .map((action) => (
              <Button
                disabled={refresh.isPending}

                key={action.action}

                onClick={() => refresh.mutate()}

                size="small"

                variant="outlined"
              >
                {tr(refresh.isPending ? "Refreshing…" : action.label)}
              </Button>
            ))}
        </Stack>
      </Stack>
    </Paper>
  );
}

function BoxTitle({ dataset }: { dataset: DatasetDescriptor }) {
  useLocale();

  return (
    <Stack>
      <Typography variant="h6">{tr(dataset.label)}</Typography>

      <Typography color="text.secondary" variant="caption">
        {tr(requirementLabel(dataset))} · {tr(dataset.format ?? "managed data")}
      </Typography>
    </Stack>
  );
}

export function DataStep({ scenarioId }: { scenarioId: string }) {
  useLocale();

  const queryClient = useQueryClient();

  const datasets = useDatasetsQuery(scenarioId);

  const [showReadyDatasets, setShowReadyDatasets] = useState(false);

  const validate = useMutation({
    mutationFn: () => validateDatasets(scenarioId),

    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["scenario", scenarioId, "datasets"],
      });
    },
  });

  if (datasets.isPending)
    return <LoadingState label={tr("Checking dataset readiness…")} />;

  if (datasets.isError)
    return (
      <FailureState
        error={datasets.error}

        onRetry={() => void datasets.refetch()}
      />
    );

  if (!datasets.data.datasets.length)
    return (
      <EmptyState
        body={tr("No datasets are configured for this scenario.")}

        title={tr("No input datasets")}
      />
    );

  const blockingDatasets = datasets.data.datasets.filter(
    (dataset) => dataset.required && dataset.status !== "ready",
  );

  const noticeDatasets = datasets.data.datasets.filter(
    (dataset) =>
      !blockingDatasets.includes(dataset) && hasNonBlockingNotice(dataset),
  );

  const readyDatasets = datasets.data.datasets.filter(
    (dataset) =>
      !blockingDatasets.includes(dataset) && !noticeDatasets.includes(dataset),
  );

  return (
    <Stack spacing={2}>
      <Paper component="section" sx={{ p: 3 }}>
        <Stack
          alignItems={{ sm: "center" }}

          direction={{ sm: "row", xs: "column" }}

          justifyContent="space-between"

          spacing={2}
        >
          <BoxTitle
            dataset={{
              id: "readiness",

              label: "Data readiness",

              description:
                "Validate coverage, schema, CRS, cache state, and optional resources before previewing candidates.",

              required: true,

              status: datasets.data.ready ? "ready" : "invalid",

              path_display: null,

              format: null,

              layer: null,

              columns: [],

              crs: null,

              extent: null,

              metadata: {},

              issues: [],

              actions: [],

              checked_at: datasets.data.checked_at,
            }}
          />

          <Stack alignItems="center" direction="row" spacing={1}>
            <Chip
              color={datasets.data.ready ? "success" : "warning"}

              label={tr(datasets.data.ready ? "Ready" : "Action needed")}
            />

            <Button
              disabled={validate.isPending}

              onClick={() => validate.mutate()}

              variant="outlined"
            >
              {tr(validate.isPending ? "Validating…" : "Validate again")}
            </Button>
          </Stack>
        </Stack>

        {blockingDatasets.length > 0 && (
          <Alert severity="warning" sx={{ mt: 2 }}>
            {tr(blockingDatasets.length)} {tr(" required input")}
            {tr(blockingDatasets.length === 1 ? " is" : "s are")}{" "}
            {tr(
              " blocking the preview. Details and next steps are listed below.",
            )}
          </Alert>
        )}

        {validate.isError && <ApiErrorAlert error={validate.error} />}
      </Paper>

      {blockingDatasets.length > 0 && (
        <Stack divider={<Divider />} spacing={2}>
          <Typography component="h2" variant="h6">
            {tr("Blocking inputs (")}
            {tr(blockingDatasets.length)})
          </Typography>

          {blockingDatasets.map((dataset) => (
            <DatasetCard
              dataset={dataset}

              key={dataset.id}

              scenarioId={scenarioId}
            />
          ))}
        </Stack>
      )}

      {noticeDatasets.length > 0 && (
        <Accordion>
          <AccordionSummary
            aria-controls="coverage-notices-content"

            id="coverage-notices-header"
          >
            <Typography>
              {tr("Coverage notices (")}
              {tr(noticeDatasets.length)})
            </Typography>
          </AccordionSummary>

          <AccordionDetails id="coverage-notices-content">
            <Typography color="text.secondary" sx={{ mb: 2 }} variant="body2">
              {tr(
                "These resources are enabled but unavailable in the selected study area. They do not block candidate preview generation.",
              )}
            </Typography>

            <Stack divider={<Divider />} spacing={2}>
              {noticeDatasets.map((dataset) => (
                <DatasetCard
                  dataset={dataset}

                  key={dataset.id}

                  scenarioId={scenarioId}
                />
              ))}
            </Stack>
          </AccordionDetails>
        </Accordion>
      )}

      {readyDatasets.length > 0 && (
        <Accordion
          expanded={showReadyDatasets}

          onChange={(_, expanded) => setShowReadyDatasets(expanded)}
        >
          <AccordionSummary
            aria-controls="ready-datasets-content"

            id="ready-datasets-header"
          >
            <Typography>
              {tr("Ready datasets (")}
              {tr(readyDatasets.length)})
            </Typography>
          </AccordionSummary>

          <AccordionDetails id="ready-datasets-content">
            <Stack divider={<Divider />} spacing={2}>
              {readyDatasets.map((dataset) => (
                <DatasetCard
                  dataset={dataset}

                  key={dataset.id}

                  scenarioId={scenarioId}
                />
              ))}
            </Stack>
          </AccordionDetails>
        </Accordion>
      )}
    </Stack>
  );
}
