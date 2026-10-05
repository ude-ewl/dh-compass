import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
  Box,
  Button,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useState } from "react";

import { formatNumber } from "./format";

export interface ChartDatum {
  label: string;
  value: number | null | undefined;
  detail?: string;
}

export function AccessibleBarChart({
  title,
  data,
  valueLabel = "Value",
  formatValue = (value) => formatNumber(value, 1),
  showDataToggle = true,
}: {
  title: string;
  data: ChartDatum[];
  valueLabel?: string;
  formatValue?: (value: number) => string;
  showDataToggle?: boolean;
}) {
  useLocale();
  const [showData, setShowData] = useState(false);
  const valid = data.filter(
    (item): item is ChartDatum & { value: number } =>
      typeof item.value === "number" && Number.isFinite(item.value),
  );
  const max = Math.max(...valid.map((item) => Math.abs(item.value)), 1);

  return (
    <Paper
      component="section"
      elevation={0}
      sx={{ border: 1, borderColor: "divider", p: 2 }}
    >
      <Typography component="h2" gutterBottom variant="h6">
        {tr(title)}
      </Typography>
      {valid.length === 0 ? (
        <Typography color="text.secondary">
          {tr("No values were reported for this chart.")}
        </Typography>
      ) : (
        <>
          <Stack
            aria-label={tr(
              showDataToggle
                ? `${title} chart. Use View data for the accessible table.`
                : `${title} chart. Values are listed beside each bar.`,
            )}
            role="img"
            spacing={1}
            sx={{ mb: 2 }}
          >
            {valid.map((item) => (
              <Stack
                alignItems="center"
                direction="row"
                key={item.label}
                spacing={1}
              >
                <Typography
                  sx={{ minWidth: { sm: 150, xs: 100 } }}
                  variant="body2"
                >
                  {tr(item.label)}
                </Typography>
                <Box
                  aria-hidden="true"
                  sx={{
                    backgroundColor: "primary.main",
                    borderRadius: 1,
                    height: 16,
                    minWidth: 2,
                    width: `${Math.max((Math.abs(item.value) / max) * 100, 1)}%`,
                  }}
                />
                <Typography fontWeight={600} variant="body2">
                  {tr(formatValue(item.value))}
                </Typography>
              </Stack>
            ))}
          </Stack>
          {showDataToggle && (
            <Button
              aria-expanded={showData}
              onClick={() => setShowData((value) => !value)}
              size="small"
              sx={{ alignSelf: "flex-start" }}
              variant="text"
            >
              {tr(showData ? "Hide data" : "View data")}
            </Button>
          )}
          {showData && (
            <Table aria-label={tr(`${title} data table`)} size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{tr("Category")}</TableCell>
                  <TableCell align="right">{tr(valueLabel)}</TableCell>
                  <TableCell>{tr("Notes")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.map((item) => (
                  <TableRow key={item.label}>
                    <TableCell>{tr(item.label)}</TableCell>
                    <TableCell align="right">
                      {tr(
                        item.value === undefined || item.value === null
                          ? "—"
                          : formatValue(item.value),
                      )}
                    </TableCell>
                    <TableCell>{tr(item.detail ?? "")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </>
      )}
    </Paper>
  );
}
