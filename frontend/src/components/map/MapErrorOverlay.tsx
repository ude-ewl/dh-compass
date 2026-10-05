import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { Alert, Box, Button, Typography } from "@mui/material";
import type { ReactNode } from "react";

interface MapErrorOverlayProps {
  message?: string;
  onRetry?: () => void;
  children?: ReactNode;
}

/** A local map failure must not hide coordinate controls or the rest of a page. */
export function MapErrorOverlay({
  message = "Map tiles are unavailable. You can still enter and edit the exact extent.",
  onRetry,
  children,
}: MapErrorOverlayProps) {
  useLocale();
  return (
    <Box
      aria-live="polite"
      sx={{
        backgroundColor: "rgba(22, 33, 62, 0.94)",
        border: 1,
        borderColor: "divider",
        borderRadius: 1,
        left: { sm: 16, xs: 8 },
        maxWidth: 360,
        p: 1.5,
        position: "absolute",
        top: { sm: 16, xs: 8 },
        zIndex: 4,
      }}
    >
      <Alert severity="warning" sx={{ alignItems: "flex-start", p: 0 }}>
        <Typography variant="body2">{tr(message)}</Typography>
        {tr(children)}
        {onRetry && (
          <Button onClick={onRetry} size="small" sx={{ mt: 0.5 }}>
            {tr("Retry map")}
          </Button>
        )}
      </Alert>
    </Box>
  );
}
