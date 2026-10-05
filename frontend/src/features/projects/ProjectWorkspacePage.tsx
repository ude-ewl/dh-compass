import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
  Alert,
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";

import {
  archiveProject,
  createScenario,
  deleteProject,
  duplicateScenario,
  importScenario,
  scenarioConfigTomlUrl,
  updateProject,
} from "../../api/client";
import { useProjectQuery, useProjectRunsQuery } from "../../api/queries";
import { ApiErrorAlert } from "../../components/feedback/ApiErrorAlert";
import {
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";
import { t } from "../../i18n/messages";

function NewScenarioDialog({
  projectId,
  open,
  onClose,
}: {
  projectId: string;
  open: boolean;
  onClose: () => void;
}) {
  useLocale();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      createScenario(projectId, {
        name: name.trim(),
        description: description.trim() || undefined,
      }),
    onSuccess: async (scenario) => {
      await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      setName("");
      setDescription("");
      onClose();
      navigate(`/projects/${projectId}/scenarios/${scenario.id}/area`);
    },
  });

  const close = () => {
    if (!mutation.isPending) {
      mutation.reset();
      setName("");
      setDescription("");
      onClose();
    }
  };

  return (
    <Dialog fullWidth maxWidth="sm" onClose={close} open={open}>
      <DialogTitle>{t("newScenario")}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {mutation.isError && (
            <Alert severity="error">{tr(mutation.error.message)}</Alert>
          )}
          <TextField
            autoFocus
            fullWidth
            label={t("scenarioName")}
            onChange={(event) => setName(event.target.value)}
            required
            value={name}
          />
          <TextField
            fullWidth
            label={t("scenarioDescription")}
            multiline
            onChange={(event) => setDescription(event.target.value)}
            value={description}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>{t("cancel")}</Button>
        <Button
          disabled={!name.trim() || mutation.isPending}
          onClick={() => mutation.mutate()}
          variant="contained"
        >
          {tr(mutation.isPending ? t("saving") : t("create"))}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function ImportScenarioDialog({
  projectId,
  open,
  onClose,
}: {
  projectId: string;
  open: boolean;
  onClose: () => void;
}) {
  useLocale();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");
  const [toml, setToml] = useState("");
  const [name, setName] = useState("");
  const [readError, setReadError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () =>
      importScenario(projectId, toml, { name: name.trim() || undefined }),
    onSuccess: async (scenario) => {
      await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      close();
      navigate(`/projects/${projectId}/scenarios/${scenario.id}/area`);
    },
  });

  const close = () => {
    if (!mutation.isPending) {
      mutation.reset();
      setFileName("");
      setToml("");
      setName("");
      setReadError(null);
      if (inputRef.current) inputRef.current.value = "";
      onClose();
    }
  };

  const selectFile = (file: File | undefined) => {
    if (!file) return;
    setFileName(file.name);
    setReadError(null);
    const reader = new FileReader();
    reader.onload = () =>
      setToml(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => setReadError(t("fileReadFailed"));
    reader.readAsText(file);
  };

  return (
    <Dialog fullWidth maxWidth="sm" onClose={close} open={open}>
      <DialogTitle>{t("importScenario")}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {readError && <Alert severity="error">{tr(readError)}</Alert>}
          {mutation.isError && <ApiErrorAlert error={mutation.error} />}
          <Button component="label" variant="outlined">
            {tr(fileName || t("chooseTomlFile"))}
            <input
              accept=".toml,text/plain"
              hidden
              onChange={(event) => selectFile(event.target.files?.[0])}
              ref={inputRef}
              type="file"
            />
          </Button>
          <TextField
            fullWidth
            label={t("scenarioNameOptional")}
            onChange={(event) => setName(event.target.value)}
            value={name}
          />
          <Typography color="text.secondary" variant="body2">
            {t("importValidationHint")}
          </Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>{t("cancel")}</Button>
        <Button
          disabled={!toml.trim() || mutation.isPending}
          onClick={() => mutation.mutate()}
          variant="contained"
        >
          {tr(mutation.isPending ? t("validating") : t("import"))}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function ProjectWorkspacePage() {
  useLocale();
  const { projectId } = useParams();
  const project = useProjectQuery(projectId);
  const runs = useProjectRunsQuery(projectId);
  const queryClient = useQueryClient();
  const [newScenarioOpen, setNewScenarioOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [projectName, setProjectName] = useState("");
  const rename = useMutation({
    mutationFn: (name: string) => updateProject(projectId ?? "", { name }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
  });

  useEffect(() => {
    if (project.data && !rename.isPending) setProjectName(project.data.name);
  }, [project.data, rename.isPending]);

  const duplicate = useMutation({
    mutationFn: (scenarioId: string) => duplicateScenario(scenarioId),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
  });
  const archive = useMutation({
    mutationFn: () => archiveProject(projectId ?? ""),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
  });
  const remove = useMutation({
    mutationFn: () => deleteProject(projectId ?? ""),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      window.location.assign("/projects");
    },
  });

  if (!projectId)
    return <FailureState error={new Error(t("missingProjectId"))} />;
  if (project.isPending) return <LoadingState label={t("loadingProject")} />;
  if (project.isError)
    return (
      <FailureState
        error={project.error}
        onRetry={() => void project.refetch()}
      />
    );

  const scenarios = project.data.scenarios;
  return (
    <Stack spacing={3}>
      <Stack
        alignItems={{ sm: "center" }}
        direction={{ sm: "row" }}
        justifyContent="space-between"
        spacing={2}
      >
        <Box>
          <TextField
            aria-label={t("projectName")}
            onBlur={() => {
              const value = projectName.trim();
              if (value && value !== project.data.name) rename.mutate(value);
            }}
            onChange={(event) => setProjectName(event.target.value)}
            sx={{
              "& .MuiInputBase-input": {
                fontSize: "2.125rem",
                fontWeight: 500,
              },
            }}
            value={projectName || project.data.name}
            variant="standard"
          />
          {project.data.description && (
            <Typography color="text.secondary">
              {project.data.description}
            </Typography>
          )}
        </Box>
        <Stack direction="row" flexWrap="wrap" gap={1}>
          <Button onClick={() => setImportOpen(true)} variant="outlined">
            {t("importScenario")}
          </Button>
          <Button onClick={() => setNewScenarioOpen(true)} variant="contained">
            {t("newScenario")}
          </Button>
        </Stack>
      </Stack>

      <Stack direction={{ md: "row", xs: "column" }} spacing={2}>
        <Card sx={{ flex: 1 }}>
          <CardContent>
            <Typography gutterBottom variant="h6">
              {t("scenarios")}
            </Typography>
            {scenarios.length === 0 ? (
              <Typography color="text.secondary">{t("noScenarios")}</Typography>
            ) : (
              <Stack divider={<Divider />} spacing={1}>
                {scenarios.map((scenario) => (
                  <Card key={scenario.id} variant="outlined">
                    <CardContent>
                      <Stack
                        alignItems="flex-start"
                        direction="row"
                        justifyContent="space-between"
                        spacing={2}
                      >
                        <Box>
                          <Typography variant="h6">{scenario.name}</Typography>
                          <Typography color="text.secondary" variant="body2">
                            {scenario.description || t("noScenarioDescription")}
                          </Typography>
                        </Box>
                        <Typography color="text.secondary" variant="body2">
                          {tr(
                            scenario.readiness_state === "stale"
                              ? t("stale")
                              : t("draft"),
                          )}
                        </Typography>
                      </Stack>
                      <Typography sx={{ mt: 1 }} variant="body2">
                        {t("revision")}: {tr(scenario.revision_number)} ·
                        {tr(" ")}
                        {t("expertOverrides")}:{" "}
                        {tr(scenario.expert_override_count)}
                      </Typography>
                    </CardContent>
                    <CardActions>
                      <Button
                        component={RouterLink}
                        to={`/projects/${projectId}/scenarios/${scenario.id}/area`}
                      >
                        {t("open")}
                      </Button>
                      <Button
                        disabled={duplicate.isPending}
                        onClick={() => duplicate.mutate(scenario.id)}
                      >
                        {t("duplicate")}
                      </Button>
                      <Button
                        component="a"
                        href={scenarioConfigTomlUrl(scenario.id)}
                      >
                        {t("exportToml")}
                      </Button>
                    </CardActions>
                  </Card>
                ))}
              </Stack>
            )}
          </CardContent>
        </Card>

        <Card sx={{ flex: 1 }}>
          <CardContent>
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
            {runs.data && runs.data.items.length > 0 && (
              <Table aria-label={t("runHistory")} size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t("runName")}</TableCell>
                    <TableCell>{t("status")}</TableCell>
                    <TableCell>{t("revision")}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {runs.data.items.map((run) => (
                    <TableRow key={run.id}>
                      <TableCell>{run.name}</TableCell>
                      <TableCell>{tr(run.status)}</TableCell>
                      <TableCell>
                        {tr(run.scenario_revision_id.slice(0, 8))}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </Stack>

      <Stack direction="row" spacing={1}>
        <Button
          color="warning"
          disabled={archive.isPending}
          onClick={() => archive.mutate()}
          variant="outlined"
        >
          {t("archiveProject")}
        </Button>
        <Button
          color="error"
          disabled={remove.isPending}
          onClick={() => {
            if (window.confirm(t("deleteProjectConfirm"))) remove.mutate();
          }}
          variant="text"
        >
          {t("deleteProject")}
        </Button>
      </Stack>

      <NewScenarioDialog
        onClose={() => setNewScenarioOpen(false)}
        open={newScenarioOpen}
        projectId={projectId}
      />
      <ImportScenarioDialog
        onClose={() => setImportOpen(false)}
        open={importOpen}
        projectId={projectId}
      />
    </Stack>
  );
}
