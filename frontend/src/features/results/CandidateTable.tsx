import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
  Chip,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

import type { CandidateRecord } from "../../api/results";
import {
  formatMetricValue,
  MetricDefinitionsDisclosure,
} from "./MetricDisplay";

export { CandidateInspector } from "./CandidateInspector";

const candidateTableMetrics = [
  "candidate.annual_heat_demand_mwh",
  "candidate.buildings",
  "candidate.central_cost",
  "candidate.decentral_cost",
] as const;

export function CandidateTable({
  candidates,
  selectedCandidateId,
  onSelect,
}: {
  candidates: CandidateRecord[];
  selectedCandidateId: number | null;
  onSelect: (candidateId: number) => void;
}) {
  useLocale();
  return (
    <Paper
      component="section"
      elevation={0}
      sx={{ border: 1, borderColor: "divider", overflowX: "auto" }}
    >
      <Stack spacing={0.75} sx={{ p: 2, pb: 1 }}>
        <Typography component="h2" variant="h6">
          {tr("Candidate decisions")}
        </Typography>
        <Typography color="text.secondary" variant="body2">
          {tr(
            "Select a row to keep the map and candidate evidence synchronized. Demand is annual; both cost columns are candidate-local annualized alternatives, not final-system totals.",
          )}
        </Typography>
        <MetricDefinitionsDisclosure metrics={[...candidateTableMetrics]} />
      </Stack>
      <Table aria-label={tr("Candidate decisions")} size="small">
        <caption
          style={{
            height: 1,
            overflow: "hidden",
            position: "absolute",
            width: 1,
          }}
        >
          {tr(
            "Candidate-local demand, building count, and annualized central and decentralized alternatives. Use the map or select a row for details.",
          )}
        </caption>
        <TableHead>
          <TableRow>
            <TableCell>{tr("Candidate")}</TableCell>
            <TableCell>{tr("Status")}</TableCell>
            <TableCell align="right">{tr("Demand (MWh/a)")}</TableCell>
            <TableCell align="right">{tr("Buildings")}</TableCell>
            <TableCell align="right">{tr("Central (€/a)")}</TableCell>
            <TableCell align="right">{tr("Decentralized (€/a)")}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {candidates.map((candidate) => (
            <TableRow
              aria-label={tr(
                `Candidate #${candidate.id}, ${candidate.decision}`,
              )}
              aria-selected={candidate.id === selectedCandidateId}
              hover
              key={candidate.id}
              onClick={() => onSelect(candidate.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(candidate.id);
                }
              }}
              selected={candidate.id === selectedCandidateId}
              tabIndex={0}
              sx={{ cursor: "pointer" }}
            >
              <TableCell>#{tr(candidate.id)}</TableCell>
              <TableCell>
                <Chip
                  color={
                    candidate.decision === "connected" ? "success" : "error"
                  }
                  label={tr(candidate.decision)}
                  size="small"
                />
              </TableCell>
              <TableCell align="right">
                {tr(
                  formatMetricValue(
                    "candidate.annual_heat_demand_mwh",
                    candidate.annual_heat_demand_mwh,
                  ),
                )}
              </TableCell>
              <TableCell align="right">
                {tr(
                  formatMetricValue("candidate.buildings", candidate.buildings),
                )}
              </TableCell>
              <TableCell align="right">
                {tr(
                  formatMetricValue(
                    "candidate.central_cost",
                    candidate.central_cost,
                  ),
                )}
              </TableCell>
              <TableCell align="right">
                {tr(
                  formatMetricValue(
                    "candidate.decentral_cost",
                    candidate.decentral_cost,
                  ),
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Paper>
  );
}
