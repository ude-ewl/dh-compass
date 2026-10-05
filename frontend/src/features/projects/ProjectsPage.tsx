import { tr } from "../../i18n/translate";
import { useLocale, getFormatLocale } from "../../i18n/locale";
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
import { useState } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";

import { createProject } from "../../api/client";
import { useProjectsQuery } from "../../api/queries";
import {
  EmptyState,
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";
import { t } from "../../i18n/messages";

function CreateProjectDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  useLocale();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      createProject({
        name: name.trim(),
        description: description.trim() || undefined,
      }),
    onSuccess: async (project) => {
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      setName("");
      setDescription("");
      onClose();
      navigate(`/projects/${project.id}`);
    },
  });

  const close = () => {
    if (!mutation.isPending) {
      setName("");
      setDescription("");
      mutation.reset();
      onClose();
    }
  };

  return (
    <Dialog fullWidth maxWidth="sm" onClose={close} open={open}>
      <DialogTitle>{t("createProject")}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {mutation.isError && (
            <Alert severity="error">{tr(mutation.error.message)}</Alert>
          )}
          <TextField
            autoFocus
            fullWidth
            label={t("projectName")}
            onChange={(event) => setName(event.target.value)}
            required
            value={name}
          />
          <TextField
            fullWidth
            label={t("projectDescription")}
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

export function ProjectsPage() {
  useLocale();
  const projects = useProjectsQuery();
  const [createOpen, setCreateOpen] = useState(false);

  if (projects.isPending) {
    return <LoadingState label={t("loadingProjects")} />;
  }
  if (projects.isError) {
    return (
      <FailureState
        error={projects.error}
        onRetry={() => void projects.refetch()}
      />
    );
  }

  const items = projects.data.items;
  return (
    <Stack spacing={3}>
      <Stack
        alignItems={{ sm: "center" }}
        direction={{ sm: "row" }}
        justifyContent="space-between"
        spacing={2}
      >
        <div>
          <Typography variant="h4">{t("projects")}</Typography>
          <Typography color="text.secondary">{t("projectsIntro")}</Typography>
        </div>
        <Button onClick={() => setCreateOpen(true)} variant="contained">
          {t("createProject")}
        </Button>
      </Stack>

      {items.length === 0 ? (
        <EmptyState
          action={
            <Button onClick={() => setCreateOpen(true)} variant="contained">
              {t("createFirstProject")}
            </Button>
          }
          body={t("projectsEmptyBody")}
          title={t("projectsEmptyTitle")}
        />
      ) : (
        <Table aria-label={t("projects")} size="medium">
          <TableHead>
            <TableRow>
              <TableCell>{t("projectName")}</TableCell>
              <TableCell>{t("scenarios")}</TableCell>
              <TableCell>{t("projectStatus")}</TableCell>
              <TableCell>{t("updated")}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {items.map((project) => (
              <TableRow hover key={project.id}>
                <TableCell>
                  <Button component={RouterLink} to={`/projects/${project.id}`}>
                    {project.name}
                  </Button>
                  {project.description && (
                    <Typography
                      color="text.secondary"
                      display="block"
                      variant="body2"
                    >
                      {project.description}
                    </Typography>
                  )}
                </TableCell>
                <TableCell>{tr(project.scenario_count)}</TableCell>
                <TableCell>
                  {tr(project.archived ? t("archived") : t("active"))}
                </TableCell>
                <TableCell>
                  {tr(
                    new Date(project.updated_at).toLocaleString(
                      getFormatLocale(),
                    ),
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <CreateProjectDialog
        onClose={() => setCreateOpen(false)}
        open={createOpen}
      />
    </Stack>
  );
}
