import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { Button, Stack } from "@mui/material";
import type { ReactNode } from "react";

interface MapControlsProps {
  onFit?: () => void;
  fitDisabled?: boolean;
  children?: ReactNode;
}

/** Small shared map actions; feature-specific actions stay in their toolbar. */
export function MapControls({
  onFit,
  fitDisabled = false,
  children,
}: MapControlsProps) {
  useLocale();
  return (
    <Stack
      aria-label={tr("Map controls")}
      direction="row"
      spacing={0.75}
      sx={{
        backgroundColor: "rgba(255,255,255,0.94)",
        border: 1,
        borderColor: "divider",
        borderRadius: 1,
        p: 0.5,
      }}
    >
      {onFit && (
        <Button disabled={fitDisabled} onClick={onFit} size="small">
          {tr("Fit selected area")}
        </Button>
      )}
      {tr(children)}
    </Stack>
  );
}
