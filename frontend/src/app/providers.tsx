import { useLocale } from "../i18n/locale";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import { RouterProvider } from "react-router-dom";

import { router } from "./router";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
    },
  },
});

const theme = createTheme({
  palette: {
    mode: "dark",
    primary: { main: "#e94560" },
    secondary: { main: "#8892b0" },
    success: { main: "#00c853" },
    warning: { main: "#ffd600" },
    error: { main: "#ff1744" },
    background: { default: "#1a1a2e", paper: "#16213e" },
    text: { primary: "#e0e0e0", secondary: "#8892b0" },
    divider: "#0f3460",
  },
  typography: {
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: 13,
  },
  shape: { borderRadius: 4 },
  components: {
    MuiButton: {
      defaultProps: { size: "small" },
      styleOverrides: { root: { textTransform: "none" } },
    },
    MuiPaper: { styleOverrides: { root: { backgroundImage: "none" } } },
  },
});

export function AppProviders() {
  useLocale();
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <RouterProvider router={router} />
      </ThemeProvider>
    </QueryClientProvider>
  );
}
