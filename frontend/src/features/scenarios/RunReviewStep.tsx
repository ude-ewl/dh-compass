import { tr } from "../../i18n/translate";

import { useLocale } from "../../i18n/locale";

import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  FormControlLabel,
  Checkbox,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useRef, useState, type ReactNode } from "react";

import { useNavigate } from "react-router-dom";

import { createRun } from "../../api/client";

import {
  useConfigurationSchemaQuery,
  useDatasetsQuery,
  usePreviewQuery,
} from "../../api/queries";

import type { ScenarioSummary } from "../../api/projects";

import { ApiErrorAlert } from "../../components/feedback/ApiErrorAlert";

import { LoadingState } from "../../components/feedback/StateViews";

import { t } from "../../i18n/messages";

export function RunReviewStep({
  projectId,

  scenario,

  onExpertSettings,
}: {
  projectId: string;

  scenario: ScenarioSummary;

  onExpertSettings?: () => void;
}) {
  useLocale();

  const navigate = useNavigate();

  const queryClient = useQueryClient();

  const datasets = useDatasetsQuery(scenario.id);

  const preview = usePreviewQuery(scenario.preview_id ?? undefined);

  const configurationSchema = useConfigurationSchemaQuery(scenario.id);

  const [name, setName] = useState(`${scenario.name} run`);

  const [description, setDescription] = useState("");

  const [acknowledged, setAcknowledged] = useState(false);

  const idempotencyKey = useRef<string | null>(null);

  const runMutation = useMutation({
    mutationFn: () => {
      if (!idempotencyKey.current) {
        idempotencyKey.current =
          typeof crypto !== "undefined" && "randomUUID" in crypto
            ? crypto.randomUUID()
            : `${Date.now()}-${Math.random()}`;
      }

      return createRun(
        scenario.id,

        {
          scenario_revision_id: scenario.current_revision_id ?? "",

          preview_id: scenario.preview_id ?? "",

          name: name.trim() || `${scenario.name} run`,

          description: description.trim() || undefined,

          warning_acknowledgements: acknowledged ? requiredWarningCodes : [],
        },

        idempotencyKey.current,
      );
    },

    onSuccess: async (run) => {
      await queryClient.invalidateQueries({
        queryKey: ["scenario", scenario.id, "runs"],
      });

      await queryClient.invalidateQueries({
        queryKey: ["scenario", scenario.id],
      });

      navigate(`/runs/${encodeURIComponent(run.id)}/monitor`);
    },
  });

  const previewReady = preview.data?.status === "ready";

  const dataReady = datasets.data?.ready === true;

  const requiredWarningCodes = (preview.data?.warnings ?? [])

    .filter(
      (issue) => issue.severity === "warning" || issue.severity === "error",
    )

    .map((issue) => issue.code);

  const document = scenario.revision?.document ?? {};

  const scenarioDocument = document.scenario;

  const enabledResources =
    scenarioDocument && typeof scenarioDocument === "object"
      ? (scenarioDocument as Record<string, unknown>).enabled_resources
      : null;

  const expertOverrides = (configurationSchema.data?.fields ?? []).filter(
    (field) => field.expert_only && field.changed_from_default,
  );

  const blockingReasons = [
    !scenario.current_revision_id
      ? "The scenario has no saved revision."
      : null,

    !dataReady ? "Required datasets are not ready." : null,

    !previewReady ? "A current candidate preview is required." : null,

    scenario.run_required && !previewReady
      ? "The scenario changed after its last preview."
      : null,
  ].filter((value): value is string => value !== null);

  const hasBlockingConditions = blockingReasons.length > 0;

  return (
    <Stack spacing={2}>
      <Paper component="section" sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Box>
            <Stack
              alignItems={{ sm: "center" }}

              direction={{ sm: "row", xs: "column" }}

              justifyContent="space-between"

              spacing={1}
            >
              <Typography component="h2" variant="h6">
                {tr("Review and run")}
              </Typography>

              {onExpertSettings && (
                <Button
                  onClick={onExpertSettings}

                  size="small"

                  variant="outlined"
                >
                  {tr("Expert settings")}
                </Button>
              )}
            </Stack>

            <Typography color="text.secondary" variant="body2">
              {tr(
                "Confirm the inputs used by this immutable run. Closing the browser after submission does not stop the worker.",
              )}
            </Typography>
          </Box>

          <Divider />

          <ReviewRow label={tr("Study area")}>
            {Object.keys(scenario.area_summary).length > 0 ? (
              <Chip color="success" label={tr("Configured")} size="small" />
            ) : (
              <Chip color="warning" label={tr("Missing")} size="small" />
            )}
          </ReviewRow>

          <ReviewRow label={tr("Data readiness")}>
            {datasets.isPending ? (
              <LoadingState label={tr("Checking datasets…")} />
            ) : (
              <Chip
                color={dataReady ? "success" : "warning"}

                label={tr(dataReady ? "Ready" : "Needs attention")}

                size="small"
              />
            )}
          </ReviewRow>

          <ReviewRow label={tr("Linear heat density threshold")}>
            <Typography variant="body2">
              {tr(scenario.effective_lhd_threshold ?? "—")} {tr(" MWh/(m·a)")}
            </Typography>
          </ReviewRow>

          <ReviewRow label={tr("Enabled heat resources")}>
            <Typography align="right" variant="body2">
              {tr(
                Array.isArray(enabledResources) && enabledResources.length > 0
                  ? enabledResources.join(", ")
                  : "Unavailable",
              )}
            </Typography>
          </ReviewRow>

          <ReviewRow label={tr("Candidate preview")}>
            <Stack alignItems="flex-end" spacing={0.25}>
              <Chip
                color={previewReady ? "success" : "warning"}

                label={tr(preview.data?.status ?? "Not generated")}

                size="small"
              />

              {preview.data?.summary && (
                <Typography color="text.secondary" variant="caption">
                  {tr(preview.data.summary.candidate_count)}{" "}
                  {tr(" candidates · threshold")}
                  {tr(" ")}
                  {tr(preview.data.linear_heat_density_threshold ?? "—")}{" "}
                  {tr(" MWh/(m·a)")}
                </Typography>
              )}
            </Stack>
          </ReviewRow>

          <ReviewRow label={tr("Expert overrides")}>
            <Typography variant="body2">
              {tr(
                scenario.expert_override_count === 0
                  ? "None"
                  : `${scenario.expert_override_count} saved override(s)`,
              )}
            </Typography>
          </ReviewRow>

          {expertOverrides.length > 0 && (
            <Paper component="section" sx={{ p: 2 }} variant="outlined">
              <Typography gutterBottom variant="subtitle2">
                {tr("Saved Expert assumptions")}
              </Typography>

              <Stack spacing={0.5}>
                {expertOverrides.map((field) => (
                  <Stack
                    alignItems={{ sm: "center" }}

                    direction={{ sm: "row", xs: "column" }}

                    justifyContent="space-between"

                    key={field.key}

                    spacing={1}
                  >
                    <Typography variant="body2">
                      {tr(field.label)} <code>{tr(field.key)}</code>
                    </Typography>

                    <Typography color="text.secondary" variant="body2">
                      {tr(JSON.stringify(field.value))} ·{tr(" ")}
                      {tr(
                        field.impact === "preview" ? "new preview" : "new run",
                      )}
                    </Typography>
                  </Stack>
                ))}
              </Stack>
            </Paper>
          )}

          {blockingReasons.length > 0 && (
            <Alert severity="warning">
              <Typography fontWeight={600}>
                {tr("Run cannot start yet.")}
              </Typography>

              <Box component="ul" sx={{ m: 0, pl: 2 }}>
                {blockingReasons.map((reason) => (
                  <li key={reason}>{tr(reason)}</li>
                ))}
              </Box>
            </Alert>
          )}

          {datasets.data?.blocking_issues.map((issue) => (
            <Alert key={`${issue.code}-${issue.path ?? ""}`} severity="error">
              {tr(issue.message)}

              {tr(issue.remediation ? ` ${issue.remediation}` : "")}
            </Alert>
          ))}

          {preview.data?.warnings.map((issue) => (
            <Alert
              key={`${issue.code}-${issue.path ?? ""}`}

              severity={issue.severity === "error" ? "error" : "warning"}
            >
              {tr(issue.message)}

              {tr(issue.remediation ? ` ${issue.remediation}` : "")}
            </Alert>
          ))}

          <TextField
            fullWidth

            label={t("runName")}

            onChange={(event) => setName(event.target.value)}

            value={name}
          />

          <TextField
            fullWidth

            label={tr("Description (optional)")}

            multiline

            onChange={(event) => setDescription(event.target.value)}

            value={description}
          />

          <FormControlLabel
            control={
              <Checkbox
                checked={acknowledged}

                onChange={(event) => setAcknowledged(event.target.checked)}
              />
            }

            label={tr(
              "I reviewed the area, data, preview, and important assumptions.",
            )}
          />

          {runMutation.isError && <ApiErrorAlert error={runMutation.error} />}

          <Stack direction={{ sm: "row", xs: "column" }} spacing={1}>
            <Button
              disabled={
                hasBlockingConditions || !acknowledged || runMutation.isPending
              }

              onClick={() => runMutation.mutate()}

              variant="contained"
            >
              {tr(
                runMutation.isPending ? "Starting run…" : "Start optimization",
              )}
            </Button>

            <Button
              onClick={() =>
                navigate(
                  `/projects/${encodeURIComponent(projectId)}/scenarios/${encodeURIComponent(scenario.id)}/candidates`,
                )
              }

              variant="outlined"
            >
              {tr("Review preview")}
            </Button>
          </Stack>
        </Stack>
      </Paper>
    </Stack>
  );
}

function ReviewRow({
  label,

  children,
}: {
  label: string;

  children: ReactNode;
}) {
  useLocale();

  return (
    <Stack
      alignItems="center"

      direction="row"

      justifyContent="space-between"

      spacing={2}
    >
      <Typography color="text.secondary">{tr(label)}</Typography>

      {tr(children)}
    </Stack>
  );
}
