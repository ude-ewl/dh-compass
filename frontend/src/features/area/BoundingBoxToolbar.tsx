import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { Alert, Box, Button, Stack, Typography } from "@mui/material";

import { formatAreaKm2, type BBox, type BBoxValidationIssue } from "./bbox";

interface BoundingBoxToolbarProps {
  compact?: boolean;
  bbox: BBox | null;
  areaKm2: number | null;
  drawing: boolean;
  validationIssues?: BBoxValidationIssue[];
  submitting?: boolean;
  onDraw: () => void;
  onFit: () => void;
  onStart: () => void;
}

export function BoundingBoxToolbar({
  compact = false,
  bbox,
  areaKm2,
  drawing,
  validationIssues = [],
  submitting = false,
  onDraw,
  onFit,
  onStart,
}: BoundingBoxToolbarProps) {
  useLocale();
  const canStart =
    Boolean(bbox) && validationIssues.length === 0 && !drawing && !submitting;

  return (
    <Stack spacing={1}>
      {validationIssues.length > 0 && (
        <Alert
          aria-label={tr("Study area validation")}
          severity="error"
          sx={{ py: 0.5 }}
        >
          <Stack spacing={0.25}>
            {validationIssues.map((issue) => (
              <Typography
                key={`${issue.code}:${issue.message}`}
                variant="body2"
              >
                {tr(issue.message)}
              </Typography>
            ))}
          </Stack>
        </Alert>
      )}
      <Stack
        alignItems={compact ? "stretch" : { sm: "center", xs: "stretch" }}
        direction={compact ? "column" : { sm: "row", xs: "column" }}
        justifyContent="space-between"
        spacing={1}
      >
        <Stack
          alignItems={compact ? "stretch" : { sm: "center", xs: "stretch" }}
          direction={compact ? "column" : { sm: "row", xs: "column" }}
          spacing={1}
        >
          <Button
            aria-pressed={drawing}
            disabled={submitting}
            onClick={onDraw}
            variant={drawing ? "contained" : "outlined"}
          >
            {tr(drawing ? "Drawing new area…" : "Draw new area")}
          </Button>
          <Button disabled={!bbox} onClick={onFit} variant="text">
            {tr("Fit selected area")}
          </Button>
          <Box
            aria-label={tr("Selected area size")}
            role="status"
            sx={{ minWidth: 100, px: 1 }}
          >
            <Typography color="text.secondary" variant="caption">
              {tr("Area")}
            </Typography>
            <Typography fontWeight={600} variant="body2">
              {tr(formatAreaKm2(areaKm2))}
            </Typography>
          </Box>
        </Stack>
        <Button disabled={!canStart} onClick={onStart} variant="contained">
          {tr(submitting ? "Starting calculation…" : "Start calculation")}
        </Button>
      </Stack>
    </Stack>
  );
}
