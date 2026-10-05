import { tr } from "../../i18n/translate";

import { useLocale } from "../../i18n/locale";

import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  Chip,
  Link as MuiLink,
  Menu,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  Typography,
} from "@mui/material";

import { useState } from "react";

import { Link as RouterLink, useSearchParams } from "react-router-dom";

import type { RunManifest } from "../../api/results";

import { t } from "../../i18n/messages";

import { ResultWarnings } from "./ResultFeedback";

import { formatDate } from "./format";

import { resultSearch } from "./selection";

export type ResultTab =
  | "overview"
  | "network"
  | "decisions"
  | "supply"
  | "costs"
  | "decentral"
  | "downloads";

const tabs: { id: ResultTab; label: string }[] = [
  { id: "overview", label: "Overview" },

  { id: "network", label: "Network" },

  { id: "decisions", label: "Decisions" },

  { id: "supply", label: "Supply" },

  { id: "costs", label: "Costs" },

  { id: "decentral", label: "Decentralized" },

  { id: "downloads", label: "Downloads" },
];

/**

 * The run identity a result header may receive.

 *

 * `GET /runs/{run_id}` is served by the managed-run resource even though the

 * result pages read it as a manifest, so a run created from the map has no

 * `display_name`/`scenario`. The header resolves a title from whichever fields

 * are present rather than rendering an empty page heading.

 */

type RunIdentity = Partial<RunManifest> & {
  id?: string;

  name?: string;
};

function runTitle(run: RunIdentity): string {
  return run.display_name || run.name || run.id || "Run";
}

export function ResultHeader({
  run,

  homePath = "/runs",

  homeLabel = "Results portal",
}: {
  run: RunIdentity;

  /** Where the breadcrumb returns to; the run workspace during the redesign. */

  homePath?: string;

  homeLabel?: string;
}) {
  useLocale();

  const title = runTitle(run);

  const artifacts = run.artifacts ?? [];

  const warnings = (run.warnings ?? []).map(warningText);

  const missingCount = artifacts.filter((artifact) => {
    if (artifact.available === false) return true;

    return ["pending", "missing", "invalid", "failed"].includes(
      String(artifact.status ?? ""),
    );
  }).length;

  return (
    <Stack spacing={1.5}>
      <Breadcrumbs aria-label={tr("Breadcrumb")}>
        <MuiLink component={RouterLink} to={homePath}>
          {tr(homeLabel)}
        </MuiLink>

        <Typography color="text.primary">{tr(title)}</Typography>
      </Breadcrumbs>

      <Stack
        alignItems={{ sm: "center", xs: "flex-start" }}

        direction={{ sm: "row", xs: "column" }}

        justifyContent="space-between"

        spacing={2}
      >
        <Box>
          <Typography component="h1" variant="h4">
            {tr(title)}
          </Typography>

          <Typography color="text.secondary">
            {run.scenario || run.name || "Calculation"} {tr(" · discovered")}
            {tr(" ")}
            {tr(
              run.updated_at ? formatDate(run.updated_at) : "date unavailable",
            )}
          </Typography>
        </Box>

        <Stack
          alignItems={{ sm: "center", xs: "flex-start" }}

          direction="row"

          spacing={1}
        >
          <Chip
            color={run.status === "completed" ? "success" : "warning"}

            label={tr(run.status)}
          />

          {run.legacy && (
            <Chip label={tr("Legacy output")} variant="outlined" />
          )}
        </Stack>
      </Stack>

      {warnings.length > 0 && <ResultWarnings warnings={warnings} />}

      {missingCount > 0 && (
        <Alert severity="info">
          {tr(missingCount)} {tr(" optional artifact")}
          {tr(missingCount === 1 ? " is" : "s are")}
          {tr(" ")}
          {tr("unavailable. The available result sections remain usable.")}
        </Alert>
      )}
    </Stack>
  );
}

function warningText(value: unknown): string {
  if (typeof value === "string") return value;

  if (value && typeof value === "object" && "message" in value) {
    const message = (value as { message?: unknown }).message;

    if (typeof message === "string") return message;
  }

  return String(value);
}

export function ResultNavigation({
  runId,

  activeTab,
}: {
  runId: string;

  activeTab: ResultTab;
}) {
  useLocale();

  const [searchParams] = useSearchParams();

  const activeIndex = Math.max(
    tabs.findIndex((tab) => tab.id === activeTab),

    0,
  );

  return (
    <Tabs
      aria-label={tr("Result navigation")}

      scrollButtons="auto"

      value={activeIndex}

      variant="scrollable"
    >
      {tabs.map((tab) => (
        <Tab
          aria-label={tr(tab.label)}

          component={RouterLink}

          key={tab.id}

          label={tr(tab.label)}

          to={`/runs/${encodeURIComponent(runId)}/results/${tab.id}${resultSearch(searchParams)}`}

          value={tabs.indexOf(tab)}
        />
      ))}
    </Tabs>
  );
}

/**

 * The constrained result navigation used by the redesign route graph.

 *

 * Summary and Network details are the only primary result modes. Inputs and

 * downloads remains reachable from the secondary options menu, so provenance

 * does not compete with outcome interpretation.

 */

export function ConstrainedResultNavigation({
  runId,

  activeTab,
}: {
  runId: string;

  activeTab: ResultTab;
}) {
  useLocale();

  const [searchParams] = useSearchParams();

  const [optionsAnchor, setOptionsAnchor] = useState<HTMLElement | null>(null);

  const base = `/runs/${encodeURIComponent(runId)}`;

  const selection = resultSearch(searchParams);

  const destinations: { id: ResultTab; label: string; to: string }[] = [
    { id: "overview", label: "Run overview", to: `${base}${selection}` },

    {
      id: "network",

      label: "Network details",

      to: `${base}/network${selection}`,
    },
  ];

  const filesPath = `${base}/files${selection}`;

  const optionsOpen = Boolean(optionsAnchor);

  const closeOptions = () => setOptionsAnchor(null);

  return (
    <Stack
      aria-label={tr("Result navigation")}

      component="nav"

      direction="row"

      spacing={1}

      sx={{ flexWrap: "wrap", gap: 1 }}
    >
      {destinations.map((destination) => (
        <Button
          aria-current={destination.id === activeTab ? "page" : undefined}

          component={RouterLink}

          key={destination.id}

          size="small"

          to={destination.to}

          variant={destination.id === activeTab ? "contained" : "outlined"}
        >
          {tr(destination.label)}
        </Button>
      ))}

      <Button
        aria-controls={optionsOpen ? "result-options-menu" : undefined}

        aria-expanded={optionsOpen}

        aria-haspopup="menu"

        aria-label={tr("More result options")}

        aria-current={activeTab === "downloads" ? "page" : undefined}

        onClick={(event) => setOptionsAnchor(event.currentTarget)}

        size="small"

        variant={activeTab === "downloads" ? "contained" : "outlined"}
      >
        {tr("More")}
      </Button>

      <Menu
        anchorEl={optionsAnchor}

        id="result-options-menu"

        onClose={closeOptions}

        open={optionsOpen}
      >
        <MenuItem
          aria-current={activeTab === "downloads" ? "page" : undefined}

          component={RouterLink}

          onClick={closeOptions}

          to={filesPath}
        >
          {tr("Inputs & downloads")}
        </MenuItem>
      </Menu>
    </Stack>
  );
}

export function BackToRuns() {
  useLocale();

  return (
    <Button component={RouterLink} to="/runs">
      {t("backToResults")}
    </Button>
  );
}
