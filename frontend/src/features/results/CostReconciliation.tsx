import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { Alert, Stack, Typography } from "@mui/material";

import { formatEuro } from "./format";

export const COST_RECONCILIATION_TOLERANCE_EUR = 0.01;

export interface CostReconciliation {
  total: number;
  components: number;
  difference: number;
  reconciles: boolean;
}

export function reconcileAnnualizedCosts(
  total: unknown,
  supply: unknown,
  grid: unknown,
  tolerance = COST_RECONCILIATION_TOLERANCE_EUR,
): CostReconciliation | null {
  if (
    !isFiniteNumber(total) ||
    !isFiniteNumber(supply) ||
    !isFiniteNumber(grid)
  ) {
    return null;
  }
  const components = supply + grid;
  const difference = total - components;
  return {
    total,
    components,
    difference,
    reconciles: Math.abs(difference) <= tolerance,
  };
}

/**
 * Keep a cost-basis mismatch beside the values that caused it. A mismatch is
 * not converted into a second, apparently authoritative total elsewhere in
 * the page.
 */
export function CostReconciliationNotice({
  total,
  supply,
  grid,
}: {
  total: unknown;
  supply: unknown;
  grid: unknown;
}) {
  useLocale();
  const result = reconcileAnnualizedCosts(total, supply, grid);
  if (!result || result.reconciles) return null;

  return (
    <Alert severity="warning">
      <Stack spacing={0.5}>
        <Typography fontWeight={600}>
          {tr("Cost totals do not reconcile")}
        </Typography>
        <Typography variant="body2">
          {tr("The reported total is ")}
          {tr(formatEuro(result.total))}
          {tr(", while supply plus grid is ")}
          {tr(formatEuro(result.components))}
          {tr(". The difference is")}
          {tr(" ")}
          {tr(formatDifference(Math.abs(result.difference)))}
          {tr(
            ". These values may use different reporting scopes or rounding; review their basis before comparing them.",
          )}
        </Typography>
      </Stack>
    </Alert>
  );
}

function formatDifference(value: number): string {
  return formatEuro(value, Number.isInteger(value) ? 0 : 2);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
