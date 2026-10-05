import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
  Button,
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

import { artifactDownloadUrl } from "../../api/client";
import { useArtifactsQuery } from "../../api/queries";
import {
  EmptyState,
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";
import { ExportActions } from "./ExportActions";
import { formatFileSize } from "./format";

/** Legacy seven-tab downloads page retained behind the compatibility route. */
export function DownloadsPage({ runId }: { runId: string }) {
  useLocale();
  const artifacts = useArtifactsQuery(runId);
  if (artifacts.isPending)
    return <LoadingState label={tr("Loading artifacts…")} />;
  if (artifacts.isError)
    return (
      <FailureState
        error={artifacts.error}
        onRetry={() => void artifacts.refetch()}
      />
    );
  if (!artifacts.data?.items.length)
    return <EmptyState title={tr("No artifacts discovered")} />;
  return (
    <Stack spacing={2}>
      <Typography component="h2" variant="h5">
        {tr("Downloads")}
      </Typography>
      <Typography color="text.secondary">
        {tr(
          "Available files are read directly from this completed output folder. Missing optional files are shown explicitly.",
        )}
      </Typography>
      <ExportActions runId={runId} />
      <Paper
        component="section"
        elevation={0}
        sx={{ border: 1, borderColor: "divider", overflowX: "auto" }}
      >
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
            {artifacts.data.items.map((artifact) => (
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
    </Stack>
  );
}
