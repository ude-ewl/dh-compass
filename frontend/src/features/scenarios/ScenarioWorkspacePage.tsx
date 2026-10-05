import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
  Alert,
  Box,
  Button,
  Chip,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  Link as RouterLink,
  NavLink,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";

import {
  createPreview,
  scenarioConfigTomlUrl,
  updateScenario,
  updateScenarioConfig,
} from "../../api/client";
import {
  useConfigurationSchemaQuery,
  useScenarioConfigQuery,
  useScenarioQuery,
  useScenarioRunsQuery,
} from "../../api/queries";
import type { ScenarioSummary } from "../../api/projects";
import { ApiClientError } from "../../api/client";
import { ApiErrorAlert } from "../../components/feedback/ApiErrorAlert";
import {
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";
import { t } from "../../i18n/messages";
import { AreaStep } from "./AreaStep";
import { CandidatePreview } from "./CandidatePreview";
import { DataStep } from "./DataStep";
import { ExpertSettingsDialog } from "./ExpertSettingsDialog";
import { RunReviewStep } from "./RunReviewStep";

const steps = [
  { key: "area", label: "Area" },
  { key: "data", label: "Data" },
  { key: "candidates", label: "Candidates" },
  { key: "review", label: "Review and run" },
] as const;

type StepKey = (typeof steps)[number]["key"];

function stepState(
  scenario: ScenarioSummary,
  step: StepKey,
): "incomplete" | "stale" | "ready" {
  if (step === "area")
    return Object.keys(scenario.area_summary).length > 0
      ? "ready"
      : "incomplete";
  if (step === "data") return "incomplete";
  if (step === "candidates") {
    if (scenario.readiness_state === "stale" || scenario.preview_stale_reason)
      return "stale";
    return scenario.preview_id ? "ready" : "incomplete";
  }
  return scenario.run_required
    ? "stale"
    : scenario.readiness_state === "complete"
      ? "ready"
      : "incomplete";
}

function getThreshold(document: Record<string, unknown>): number | "" {
  const network = document.network;
  if (!network || typeof network !== "object") return "";
  const value = (network as Record<string, unknown>)
    .linear_heat_density_threshold;
  return typeof value === "number" ? value : "";
}

function setThreshold(
  document: Record<string, unknown>,
  value: number,
): Record<string, unknown> {
  const network =
    document.network && typeof document.network === "object"
      ? { ...(document.network as Record<string, unknown>) }
      : {};
  network.linear_heat_density_threshold = value;
  return { ...document, network };
}

function isRevisionConflict(error: unknown): error is ApiClientError {
  return (
    error instanceof ApiClientError &&
    error.status === 409 &&
    error.payload.code === "SCENARIO_REVISION_CONFLICT"
  );
}

function ConflictNotice({
  onReload,
  error,
}: {
  onReload: () => void;
  error: unknown;
}) {
  useLocale();
  const message =
    error instanceof ApiClientError
      ? error.payload.message
      : t("revisionConflictBody");
  return (
    <Alert
      action={
        <Button onClick={onReload} size="small">
          {t("reloadServerVersion")}
        </Button>
      }
      severity="warning"
    >
      <strong>{t("revisionConflictTitle")}</strong> {tr(message)}
    </Alert>
  );
}

function StepNavigation({
  scenario,
  projectId,
}: {
  scenario: ScenarioSummary;
  projectId: string;
}) {
  useLocale();
  const location = useLocation();
  const current = location.pathname.split("/").pop();
  return (
    <Stack
      aria-label={t("scenarioSteps")}
      direction={{ sm: "row", xs: "column" }}
      spacing={1}
    >
      {steps.map((step) => {
        const state = stepState(scenario, step.key);
        return (
          <Button
            component={NavLink}
            key={step.key}
            to={`/projects/${projectId}/scenarios/${scenario.id}/${step.key}`}
            variant={current === step.key ? "contained" : "outlined"}
          >
            {tr(step.label)} ·{tr(" ")}
            {tr(
              state === "ready"
                ? t("ready")
                : state === "stale"
                  ? t("stale")
                  : t("incomplete"),
            )}
          </Button>
        );
      })}
    </Stack>
  );
}

export function ScenarioWorkspacePage() {
  useLocale();
  const { projectId, scenarioId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const scenario = useScenarioQuery(scenarioId);
  const config = useScenarioConfigQuery(scenarioId);
  const schema = useConfigurationSchemaQuery(scenarioId);
  const runs = useScenarioRunsQuery(scenarioId);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [metadataDirty, setMetadataDirty] = useState(false);
  const [threshold, setThresholdValue] = useState<number | "">("");
  const [configDirty, setConfigDirty] = useState(false);
  const [configDocument, setConfigDocument] = useState<Record<
    string,
    unknown
  > | null>(null);
  const expertOpen = searchParams.get("expert") === "1";

  const openExpertSettings = () => {
    const next = new URLSearchParams(searchParams);
    next.set("expert", "1");
    setSearchParams(next);
  };

  const closeExpertSettings = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("expert");
    setSearchParams(next);
  };

  useEffect(() => {
    if (scenario.data && !metadataDirty) {
      setName(scenario.data.name);
      setDescription(scenario.data.description ?? "");
    }
  }, [metadataDirty, scenario.data]);

  useEffect(() => {
    if (config.data && !configDirty) {
      setConfigDocument(config.data.effective_document);
      setThresholdValue(getThreshold(config.data.effective_document));
    }
  }, [config.data, configDirty]);

  const metadataMutation = useMutation({
    mutationFn: () =>
      updateScenario(scenarioId ?? "", {
        expected_revision_id: scenario.data?.current_revision_id ?? "",
        name: name.trim(),
        description: description.trim() || null,
      }),
    onSuccess: async () => {
      setMetadataDirty(false);
      await queryClient.invalidateQueries({
        queryKey: ["scenario", scenarioId],
      });
      await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });

  const configMutation = useMutation({
    mutationFn: () =>
      updateScenarioConfig(scenarioId ?? "", {
        expected_revision_id: config.data?.revision_id ?? "",
        document: configDocument ?? {},
      }),
    onSuccess: async (result) => {
      setConfigDirty(false);
      setConfigDocument(result.revision.document);
      setThresholdValue(getThreshold(result.revision.document));
      await queryClient.invalidateQueries({
        queryKey: ["scenario", scenarioId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["scenario", scenarioId, "config"],
      });
      await queryClient.invalidateQueries({
        queryKey: ["configuration-schema", scenarioId],
      });
      await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });

  const archiveMutation = useMutation({
    mutationFn: () =>
      updateScenario(scenarioId ?? "", {
        expected_revision_id: scenario.data?.current_revision_id ?? "",
        archived: true,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      navigate(`/projects/${projectId}`);
    },
  });

  useEffect(() => {
    if (
      !metadataDirty ||
      !scenario.data ||
      !name.trim() ||
      metadataMutation.isPending
    )
      return;
    const timer = window.setTimeout(() => metadataMutation.mutate(), 600);
    return () => window.clearTimeout(timer);
  }, [metadataDirty, name, description, metadataMutation, scenario.data]);

  useEffect(() => {
    if (!configDirty || !config.data || configMutation.isPending) return;
    const timer = window.setTimeout(() => configMutation.mutate(), 700);
    return () => window.clearTimeout(timer);
  }, [configDirty, threshold, config.data, configMutation]);

  const thresholdField = useMemo(
    () =>
      schema.data?.fields.find(
        (field) => field.key === "network.linear_heat_density_threshold",
      ),
    [schema.data],
  );

  if (!projectId || !scenarioId)
    return <FailureState error={new Error(t("missingScenarioId"))} />;
  if (scenario.isPending || config.isPending)
    return <LoadingState label={t("loadingScenario")} />;
  if (scenario.isError)
    return (
      <FailureState
        error={scenario.error}
        onRetry={() => void scenario.refetch()}
      />
    );
  if (config.isError)
    return (
      <FailureState
        error={config.error}
        onRetry={() => void config.refetch()}
      />
    );

  const currentScenario = scenario.data;
  const currentStep = (window.location.pathname.split("/").pop() ??
    "area") as StepKey;
  const mutationErrors = [
    metadataMutation.error,
    configMutation.error,
    archiveMutation.error,
  ];
  const conflictError = mutationErrors.find(isRevisionConflict);
  const saveError = mutationErrors.find(
    (error) => error !== null && !isRevisionConflict(error),
  );
  const thresholdChanged =
    threshold !== "" && threshold !== currentScenario.effective_lhd_threshold;
  const configuredBBox = (() => {
    const scenarioDocument = configDocument?.scenario;
    if (!scenarioDocument || typeof scenarioDocument !== "object") return null;
    const bbox = (scenarioDocument as Record<string, unknown>).bbox;
    if (
      Array.isArray(bbox) &&
      bbox.length === 4 &&
      bbox.every((value) => typeof value === "number")
    ) {
      return bbox as [number, number, number, number];
    }
    return null;
  })();

  const reload = () => {
    setMetadataDirty(false);
    setConfigDirty(false);
    metadataMutation.reset();
    configMutation.reset();
    archiveMutation.reset();
    closeExpertSettings();
    void scenario.refetch();
    void config.refetch();
  };

  const onExpertApplied = async (
    result: Awaited<ReturnType<typeof updateScenarioConfig>>,
  ) => {
    setConfigDirty(false);
    setConfigDocument(result.revision.document);
    setThresholdValue(getThreshold(result.revision.document));
    closeExpertSettings();
    await queryClient.invalidateQueries({ queryKey: ["scenario", scenarioId] });
    await queryClient.invalidateQueries({
      queryKey: ["scenario", scenarioId, "config"],
    });
    await queryClient.invalidateQueries({
      queryKey: ["configuration-schema", scenarioId],
    });
    await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
  };

  const onThresholdChange = (value: string) => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed < 0 || !configDocument) {
      setThresholdValue(
        value === "" ? "" : Number.isFinite(parsed) ? parsed : threshold,
      );
      return;
    }
    setThresholdValue(parsed);
    setConfigDocument(setThreshold(configDocument, parsed));
    setConfigDirty(true);
  };

  const generatePreview = async () => {
    let revisionId = config.data?.revision_id;
    if (configDirty) {
      const result = await configMutation.mutateAsync();
      revisionId = result.revision.id;
    }
    if (!revisionId)
      throw new Error("The scenario configuration is not ready.");
    return createPreview(scenarioId, {
      scenario_revision_id: revisionId,
      linear_heat_density_threshold_mwh_per_m_a:
        typeof threshold === "number" ? threshold : undefined,
    });
  };

  return (
    <Stack spacing={3}>
      <Stack
        alignItems={{ sm: "center" }}
        direction={{ sm: "row" }}
        justifyContent="space-between"
        spacing={2}
      >
        <Box>
          <Typography variant="h4">
            {tr(name || currentScenario.name)}
          </Typography>
          <Typography color="text.secondary">
            {t("scenarioWorkspace")}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button
            component="a"
            href={scenarioConfigTomlUrl(scenarioId)}
            variant="outlined"
          >
            {t("exportToml")}
          </Button>
          <Button onClick={() => navigate(`/projects/${projectId}`)}>
            {t("backToProject")}
          </Button>
          <Button
            color="warning"
            disabled={archiveMutation.isPending}
            onClick={() => {
              if (window.confirm(t("archiveScenarioConfirm"))) {
                archiveMutation.mutate();
              }
            }}
            variant="outlined"
          >
            {t("archiveScenario")}
          </Button>
        </Stack>
      </Stack>

      <StepNavigation projectId={projectId} scenario={currentScenario} />

      {conflictError && (
        <ConflictNotice error={conflictError} onReload={reload} />
      )}
      {saveError && <ApiErrorAlert error={saveError} />}
      {metadataMutation.isSuccess && !metadataDirty && (
        <Alert severity="success">{t("changesSaved")}</Alert>
      )}
      {configMutation.isSuccess && !configDirty && (
        <Alert
          severity={
            configMutation.data.invalidation.preview_invalidated
              ? "warning"
              : "success"
          }
        >
          {tr(
            configMutation.data.invalidation.preview_invalidated
              ? t("previewInvalidated")
              : configMutation.data.invalidation.new_run_required
                ? t("newRunRequired")
                : t("changesSaved"),
          )}
        </Alert>
      )}

      <Paper component="section" sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="h6">{t("scenarioDetails")}</Typography>
          <TextField
            error={metadataDirty && !name.trim()}
            fullWidth
            helperText={tr(
              metadataDirty && !name.trim()
                ? t("scenarioNameRequired")
                : undefined,
            )}
            label={t("scenarioName")}
            onChange={(event) => {
              setName(event.target.value);
              setMetadataDirty(true);
              metadataMutation.reset();
            }}
            value={name}
          />
          <TextField
            fullWidth
            label={t("scenarioDescription")}
            multiline
            onChange={(event) => {
              setDescription(event.target.value);
              setMetadataDirty(true);
              metadataMutation.reset();
            }}
            value={description}
          />
          <Typography color="text.secondary" variant="body2">
            {tr(
              metadataDirty
                ? t("savingSoon")
                : t("savedAtRevision", {
                    revision: currentScenario.revision_number,
                  }),
            )}
          </Typography>
        </Stack>
      </Paper>

      {currentStep === "candidates" && (
        <Paper component="section" sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Stack
              alignItems="center"
              direction="row"
              justifyContent="space-between"
            >
              <Typography variant="h6">{t("standardConfiguration")}</Typography>
              <Chip
                label={tr(thresholdField?.unit ?? "MWh/(m·a)")}
                size="small"
                variant="outlined"
              />
            </Stack>
            <Typography color="text.secondary" variant="body2">
              {t("thresholdExplanation")}
            </Typography>
            <TextField
              error={
                threshold !== "" &&
                (typeof threshold !== "number" || threshold < 0)
              }
              helperText={tr(
                thresholdChanged
                  ? t("previewWillBeStale")
                  : thresholdField?.description,
              )}
              inputProps={{ min: 0, step: "any" }}
              label={tr(thresholdField?.label ?? t("lhdThreshold"))}
              onChange={(event) => onThresholdChange(event.target.value)}
              type="number"
              value={threshold}
            />
            <Typography color="text.secondary" variant="body2">
              {t("expertOverrideCount", {
                count: currentScenario.expert_override_count,
              })}
            </Typography>
          </Stack>
        </Paper>
      )}

      {currentStep === "area" && configuredBBox && (
        <AreaStep
          initialBBox={configuredBBox}
          revisionId={currentScenario.current_revision_id ?? ""}
          scenarioId={scenarioId}
        />
      )}
      {currentStep === "data" && <DataStep scenarioId={scenarioId} />}
      {currentStep === "candidates" && (
        <CandidatePreview
          onGenerate={generatePreview}
          onExpertSettings={openExpertSettings}
          previewId={currentScenario.preview_id}
          scenarioId={scenarioId}
        />
      )}
      {currentStep === "review" && (
        <RunReviewStep
          onExpertSettings={openExpertSettings}
          projectId={projectId}
          scenario={currentScenario}
        />
      )}

      <Paper component="section" sx={{ p: 3 }}>
        <Typography gutterBottom variant="h6">
          {t("runHistory")}
        </Typography>
        {runs.isPending && <LoadingState label={t("loadingRuns")} />}
        {runs.isError && (
          <FailureState
            error={runs.error}
            onRetry={() => void runs.refetch()}
          />
        )}
        {runs.data && runs.data.items.length === 0 && (
          <Typography color="text.secondary">{t("noRunsYet")}</Typography>
        )}
        {runs.data?.items.map((run) => (
          <Typography key={run.id} variant="body2">
            <RouterLink to={`/runs/${encodeURIComponent(run.id)}/monitor`}>
              {run.name}
            </RouterLink>
            {tr(" ")}· {tr(run.status)} · {t("revision")}
            {tr(" ")}
            {tr(run.scenario_revision_id.slice(0, 8))}
          </Typography>
        ))}
      </Paper>

      {configDocument && currentScenario.current_revision_id && (
        <ExpertSettingsDialog
          document={configDocument}
          mergedToml={config.data?.merged_toml}
          onApplied={onExpertApplied}
          onClose={closeExpertSettings}
          open={expertOpen}
          revisionId={
            config.data?.revision_id ?? currentScenario.current_revision_id
          }
          scenarioId={scenarioId}
        />
      )}
    </Stack>
  );
}
