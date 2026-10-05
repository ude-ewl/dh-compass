import { tr } from "../../i18n/translate";
import { Alert, Box, Button, Collapse, Stack, Typography } from "@mui/material";
import { Component, type ErrorInfo, type ReactNode } from "react";

interface PanelErrorBoundaryProps {
  children: ReactNode;
  /** The panel name is part of the recovery message, not just a log label. */
  title: string;
  /** Remount the panel when its route-owned data changes. */
  resetKey?: string | number;
}

interface PanelErrorBoundaryState {
  error: Error | null;
  detailsOpen: boolean;
}

/**
 * Keep an optional map, chart, or table failure local to its result panel.
 *
 * Query errors are already rendered by ResultPanelError. This boundary covers
 * the other failure class: malformed or unexpectedly large data making a
 * visualization throw while the surrounding run workspace is still useful.
 */
export class PanelErrorBoundary extends Component<
  PanelErrorBoundaryProps,
  PanelErrorBoundaryState
> {
  state: PanelErrorBoundaryState = { error: null, detailsOpen: false };

  static getDerivedStateFromError(error: Error): PanelErrorBoundaryState {
    return { error, detailsOpen: false };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep diagnostics available to operators without replacing the user's
    // workspace with a blank error page.
    console.error("Unhandled result panel error", error, info.componentStack);
  }

  componentDidUpdate(previousProps: PanelErrorBoundaryProps) {
    if (
      previousProps.resetKey !== this.props.resetKey &&
      this.state.error !== null
    ) {
      this.setState({ error: null, detailsOpen: false });
    }
  }

  private retry = () => {
    this.setState({ error: null, detailsOpen: false });
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    const message = error.message || "The panel could not be displayed.";
    return (
      <Alert aria-live="polite" severity="error">
        <Stack spacing={0.75}>
          <Typography fontWeight={600}>{tr(this.props.title)}</Typography>
          <Typography variant="body2">
            {tr(
              "This part of the result could not be displayed. The other result sections remain available.",
            )}
          </Typography>
          <Button
            onClick={this.retry}
            size="small"
            sx={{ alignSelf: "flex-start" }}
            variant="outlined"
          >
            {tr("Retry panel")}
          </Button>
          <Box>
            <Button
              aria-expanded={this.state.detailsOpen}
              onClick={() =>
                this.setState((current) => ({
                  ...current,
                  detailsOpen: !current.detailsOpen,
                }))
              }
              size="small"
              sx={{ px: 0 }}
            >
              {tr("Technical details")}
            </Button>
            <Collapse in={this.state.detailsOpen}>
              <Typography
                component="pre"
                sx={{
                  maxWidth: "100%",
                  overflow: "auto",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
                variant="caption"
              >
                {tr(message)}
              </Typography>
            </Collapse>
          </Box>
        </Stack>
      </Alert>
    );
  }
}
