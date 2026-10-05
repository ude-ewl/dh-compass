import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import type { BBoxValidationIssue } from "./bbox";

interface ExactExtentPanelProps {
  values: string[];
  issues?: BBoxValidationIssue[];
  onChange: (index: number, value: string) => void;
}

const fields = [
  ["West", "Longitude"],
  ["South", "Latitude"],
  ["East", "Longitude"],
  ["North", "Latitude"],
] as const;

/** Precision recovery without making coordinates the primary workflow. */
export function ExactExtentPanel({
  values,
  issues = [],
  onChange,
}: ExactExtentPanelProps) {
  useLocale();
  const issueText = issues.map((issue) => tr(issue.message)).join(" ");

  return (
    <Accordion
      disableGutters
      elevation={0}
      sx={{
        "&:before": { display: "none" },
        backgroundColor: "transparent",
      }}
    >
      <AccordionSummary
        aria-controls="exact-extent-content"
        expandIcon={<span aria-hidden="true">⌄</span>}
        id="exact-extent-header"
      >
        <Stack>
          <Typography fontWeight={600}>{tr("Exact extent")}</Typography>
          <Typography color="text.secondary" variant="caption">
            {tr("Edit WGS84 coordinates for precision or recovery.")}
          </Typography>
        </Stack>
      </AccordionSummary>
      <AccordionDetails id="exact-extent-content" sx={{ px: 0 }}>
        <Stack
          aria-describedby={issueText ? "exact-extent-validation" : undefined}
          direction={{ sm: "row", xs: "column" }}
          spacing={1}
        >
          {fields.map(([label, helper], index) => {
            const fieldError =
              values[index] !== "" && !Number.isFinite(Number(values[index]));
            return (
              <TextField
                error={fieldError || issues.length > 0}
                fullWidth
                helperText={tr(helper)}
                inputProps={{ inputMode: "decimal" }}
                key={label}
                label={tr(label)}
                onChange={(event) => onChange(index, event.target.value)}
                type="number"
                value={values[index] ?? ""}
              />
            );
          })}
        </Stack>
        {issueText && (
          <Typography
            color="error.main"
            id="exact-extent-validation"
            sx={{ mt: 1 }}
            variant="caption"
          >
            {tr(issueText)}
          </Typography>
        )}
      </AccordionDetails>
    </Accordion>
  );
}
