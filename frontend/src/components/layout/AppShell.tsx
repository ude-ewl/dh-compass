import { tr } from "../../i18n/translate";
import {
  AppBar,
  Box,
  Button,
  Chip,
  Container,
  IconButton,
  Link as MuiLink,
  Menu,
  MenuItem,
  Select,
  Toolbar,
  Typography,
} from "@mui/material";
import { useEffect, useRef, useState } from "react";
import {
  NavLink,
  Outlet,
  useLocation,
  useSearchParams,
} from "react-router-dom";

import { useHealthQuery } from "../../api/queries";
import { t } from "../../i18n/messages";
import { useLocale, setLocale } from "../../i18n/locale";
import { featureFlags, legacyRouteCompatibility } from "../../app/featureFlags";

function LanguageSelector() {
  const locale = useLocale();
  return (
    <Select
      value={locale}
      onChange={(event) => setLocale(event.target.value as "en" | "de")}
      inputProps={{ "aria-label": "Language / Sprache" }}
      size="small"
      sx={{ ml: 2, fontSize: 12, "& .MuiSelect-select": { py: 0.75 } }}
    >
      <MenuItem value="en">{tr("English")}</MenuItem>
      <MenuItem value="de">{tr("Deutsch")}</MenuItem>
    </Select>
  );
}

function ExpertSettingsAction() {
  useLocale();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const isScenarioRoute = /^\/projects\/[^/]+\/scenarios\/[^/]+\//.test(
    location.pathname,
  );
  if (!isScenarioRoute) return null;

  return (
    <Button
      onClick={() => {
        const next = new URLSearchParams(searchParams);
        next.set("expert", "1");
        setSearchParams(next);
      }}
      size="small"
      variant="outlined"
    >
      {tr("Expert settings")}
    </Button>
  );
}

function ApiStatus() {
  useLocale();
  const health = useHealthQuery();

  if (health.isPending) {
    return <Chip color="default" label={t("apiChecking")} size="small" />;
  }
  if (health.isError) {
    return <Chip color="warning" label={t("apiUnavailable")} size="small" />;
  }
  return <Chip color="success" label={t("apiConnected")} size="small" />;
}

function SkipToContent() {
  useLocale();
  return (
    <MuiLink className="skip-to-content" href="#main-content">
      {tr("Skip to main content")}
    </MuiLink>
  );
}

function RedesignHeader() {
  useLocale();
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const closeMenu = () => setMenuAnchor(null);

  return (
    <AppBar color="inherit" elevation={0} position="static">
      <Toolbar
        sx={{
          borderBottom: 1,
          borderColor: "divider",
          minHeight: { sm: 44, xs: 44 },
          px: { sm: 2, xs: 1.5 },
        }}
      >
        <Typography
          component={NavLink}
          sx={{ color: "inherit", textDecoration: "none" }}
          to="/"
          variant="subtitle1"
        >
          {t("appName")}
        </Typography>
        <Box sx={{ flexGrow: 1 }} />
        <Box sx={{ display: { sm: "flex", xs: "none" } }}>
          <MuiLink
            component={NavLink}
            sx={{ mr: 3, textDecoration: "none" }}
            to="/"
          >
            {tr("New run")}
          </MuiLink>
          <MuiLink
            component={NavLink}
            sx={{ mr: 3, textDecoration: "none" }}
            to="/recent"
          >
            {tr("Recent runs")}
          </MuiLink>
          <MuiLink
            component={NavLink}
            sx={{ textDecoration: "none" }}
            to="/help"
          >
            {tr("Help")}
          </MuiLink>
        </Box>
        <LanguageSelector />
        <IconButton
          aria-controls={menuAnchor ? "redesign-navigation-menu" : undefined}
          aria-expanded={Boolean(menuAnchor)}
          aria-haspopup="menu"
          aria-label={tr("Open navigation menu")}
          onClick={(event) => setMenuAnchor(event.currentTarget)}
          sx={{ display: { sm: "none", xs: "inline-flex" } }}
        >
          <span aria-hidden="true">☰</span>
        </IconButton>
        <Menu
          anchorEl={menuAnchor}
          id="redesign-navigation-menu"
          onClose={closeMenu}
          open={Boolean(menuAnchor)}
        >
          <MenuItem component={NavLink} onClick={closeMenu} to="/">
            {tr("New run")}
          </MenuItem>
          <MenuItem component={NavLink} onClick={closeMenu} to="/recent">
            {tr("Recent runs")}
          </MenuItem>
          <MenuItem component={NavLink} onClick={closeMenu} to="/help">
            {tr("Help")}
          </MenuItem>
        </Menu>
      </Toolbar>
    </AppBar>
  );
}

function LegacyShell() {
  useLocale();
  return (
    <>
      <AppBar color="inherit" elevation={0} position="static">
        <Toolbar sx={{ gap: 2 }}>
          <Typography
            component={NavLink}
            sx={{ color: "inherit", textDecoration: "none" }}
            to="/"
            variant="h6"
          >
            {t("appName")}
          </Typography>
          <Chip label={t("environment")} size="small" variant="outlined" />
          <Box sx={{ flexGrow: 1 }} />
          <ExpertSettingsAction />
          <ApiStatus />
          <LanguageSelector />
        </Toolbar>
      </AppBar>

      <Box sx={{ display: "flex", minHeight: "calc(100vh - 64px)" }}>
        <Box
          component="nav"
          aria-label={t("navigation")}
          sx={{
            borderRight: 1,
            borderColor: "divider",
            p: 2,
            width: { md: 240, xs: 0 },
            display: { xs: "none", md: "block" },
          }}
        >
          <MuiLink component={NavLink} display="block" sx={{ py: 1 }} to="/">
            {t("overview")}
          </MuiLink>
          <MuiLink
            component={NavLink}
            display="block"
            sx={{ py: 1 }}
            to="/projects"
          >
            {t("projects")}
          </MuiLink>
          <MuiLink
            component={NavLink}
            display="block"
            sx={{ py: 1 }}
            to="/runs"
          >
            {t("resultsPortal")}
          </MuiLink>
          <MuiLink
            component={NavLink}
            display="block"
            sx={{ py: 1 }}
            to="/help"
          >
            {t("help")}
          </MuiLink>
        </Box>

        <Container component="main" maxWidth="xl" sx={{ py: 4 }}>
          <Outlet />
        </Container>
      </Box>
    </>
  );
}

function RouteMainContent() {
  useLocale();
  const location = useLocation();
  const mainRef = useRef<HTMLElement | null>(null);
  const firstRender = useRef(true);

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    mainRef.current?.focus();
  }, [location.pathname, location.search, location.hash]);

  return (
    <Box
      component="main"
      id="main-content"
      ref={mainRef}
      tabIndex={-1}
      sx={{ flex: 1, minHeight: 0, outline: "none" }}
    >
      <Outlet />
    </Box>
  );
}

export function AppShell() {
  useLocale();
  const location = useLocation();
  const isRetiredWorkflowPath =
    !legacyRouteCompatibility &&
    /^\/(?:projects|compare)(?:\/|$)/.test(location.pathname);
  const useRedesignShell =
    featureFlags.frontendRedesign &&
    (isRetiredWorkflowPath ||
      location.pathname === "/" ||
      location.pathname === "/runs" ||
      location.pathname.startsWith("/recent") ||
      location.pathname.startsWith("/runs/") ||
      location.pathname === "/help");

  if (useRedesignShell) {
    return (
      <Box
        className="app-shell viewport-shell"
        sx={{ display: "flex", flexDirection: "column", height: "100vh" }}
      >
        <SkipToContent />
        <RedesignHeader />
        <RouteMainContent />
      </Box>
    );
  }

  return (
    <Box className="app-shell" sx={{ minHeight: "100vh" }}>
      <LegacyShell />
    </Box>
  );
}
