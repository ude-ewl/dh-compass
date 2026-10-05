import {
  createBrowserRouter,
  Navigate,
  type RouteObject,
} from "react-router-dom";

import { featureFlags, legacyRouteCompatibility } from "./featureFlags";
import {
  LegacyResultRedirect,
  LegacyRunRedirect,
} from "./routeMigrationComponents";
import { RouteErrorBoundary } from "../components/feedback/RouteErrorBoundary";
import { AppShell } from "../components/layout/AppShell";
import { AreaSelectionPage } from "../features/area/AreaSelectionPage";
import { ComparisonPage } from "../features/comparison/ComparisonPage";
import { HelpPage } from "../features/help/HelpPage";
import { HomePage } from "../features/home/HomePage";
import { ProjectWorkspacePage } from "../features/projects/ProjectWorkspacePage";
import { ProjectsPage } from "../features/projects/ProjectsPage";
import { RunMonitorPage } from "../features/scenarios/RunMonitorPage";
import { ScenarioWorkspacePage } from "../features/scenarios/ScenarioWorkspacePage";
import { ResultsPortalPage } from "../features/results/ResultsPortalPage";
import { RunResultsPage } from "../features/results/RunResultsPage";
import { RecentRunsPage } from "../features/runs/RecentRunsPage";
import { RunPage } from "../features/runs/RunPage";

export interface RouteGraphOptions {
  /** Select the constrained area → run → result experience. */
  frontendRedesign?: boolean;
  /** Temporarily expose the old project/scenario/comparison workflow. */
  legacyRoutes?: boolean;
}

function retiredWorkflowRedirect() {
  return <Navigate replace to="/" />;
}

function legacyWorkflowRoutes(): RouteObject[] {
  return [
    { path: "projects", element: <ProjectsPage /> },
    { path: "projects/:projectId", element: <ProjectWorkspacePage /> },
    {
      path: "projects/:projectId/scenarios/:scenarioId",
      element: <Navigate replace to="area" />,
    },
    {
      path: "projects/:projectId/scenarios/:scenarioId/:step",
      element: <ScenarioWorkspacePage />,
    },
    { path: "compare", element: <ComparisonPage /> },
    { path: "compare/:comparisonId", element: <ComparisonPage /> },
  ];
}

/**
 * Build the route graph independently of the browser router so the rollout
 * boundary can be tested without rendering the application. In the released
 * redesign graph, legacy paths are explicit redirects rather than routes that
 * accidentally expose project, scenario, or comparison decisions.
 */
export function createRouteGraph(
  options: RouteGraphOptions = {},
): RouteObject[] {
  const frontendRedesign =
    options.frontendRedesign ?? featureFlags.frontendRedesign;
  const defaultLegacyRoutes =
    frontendRedesign === featureFlags.frontendRedesign
      ? legacyRouteCompatibility
      : false;
  const keepLegacyRoutes =
    !frontendRedesign || (options.legacyRoutes ?? defaultLegacyRoutes);

  const workflowRoutes = keepLegacyRoutes
    ? legacyWorkflowRoutes()
    : [
        { path: "projects", element: retiredWorkflowRedirect() },
        { path: "projects/*", element: retiredWorkflowRedirect() },
        { path: "compare", element: retiredWorkflowRedirect() },
        { path: "compare/*", element: retiredWorkflowRedirect() },
      ];

  return [
    {
      path: "/",
      element: <AppShell />,
      errorElement: <RouteErrorBoundary />,
      children: [
        {
          index: true,
          element: frontendRedesign ? <AreaSelectionPage /> : <HomePage />,
        },
        { path: "help", element: <HelpPage /> },
        {
          path: "recent",
          element: frontendRedesign ? (
            <RecentRunsPage />
          ) : (
            <ResultsPortalPage />
          ),
        },
        ...workflowRoutes,
        {
          path: "runs",
          element: frontendRedesign ? (
            <Navigate replace to="/recent" />
          ) : (
            <ResultsPortalPage />
          ),
        },
        {
          path: "runs/:runId",
          element: frontendRedesign ? (
            <RunPage />
          ) : (
            <Navigate replace to="monitor" />
          ),
        },
        {
          path: "runs/:runId/network",
          element: frontendRedesign ? (
            <RunResultsPage forcedTab="network" />
          ) : (
            <Navigate replace to="../results/network" />
          ),
        },
        {
          path: "runs/:runId/files",
          element: frontendRedesign ? (
            <RunResultsPage forcedTab="downloads" />
          ) : (
            <Navigate replace to="../results/downloads" />
          ),
        },
        {
          path: "runs/:runId/monitor",
          element: frontendRedesign ? (
            <LegacyRunRedirect />
          ) : (
            <RunMonitorPage />
          ),
        },
        {
          path: "runs/:runId/results",
          element: frontendRedesign ? (
            <LegacyResultRedirect />
          ) : (
            <RunResultsPage />
          ),
        },
        {
          path: "runs/:runId/results/:tab",
          element: frontendRedesign ? (
            <LegacyResultRedirect />
          ) : (
            <RunResultsPage />
          ),
        },
      ],
    },
  ];
}

export const router = createBrowserRouter(
  createRouteGraph({
    frontendRedesign: featureFlags.frontendRedesign,
    legacyRoutes: legacyRouteCompatibility,
  }),
);
