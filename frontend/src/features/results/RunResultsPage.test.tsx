import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { RunResultsPage } from "./RunResultsPage";

vi.mock("../../app/featureFlags", () => ({
  featureFlags: { frontendRedesign: true },
}));

const now = "2026-01-01T10:00:00Z";

/**
 * The payload `GET /runs/{run_id}` really returns: the managed run resource,
 * which has no `display_name`/`scenario` manifest fields.
 */
const managedRun = {
  id: "run-1",
  scenario_id: "scenario-1",
  scenario_revision_id: "revision-1",
  preview_id: null,
  name: "Bad Oeynhausen study area",
  description: null,
  output_label: null,
  status: "completed",
  stage: "complete",
  progress: null,
  candidate_progress: null,
  configuration_snapshot: {},
  configuration_version: "default-v1",
  bbox: [7.1, 51.2, 7.2, 51.3],
  data_snapshot: {},
  application_version: "0.1.0",
  solver_name: null,
  solver_version: null,
  process_identity: null,
  started_at: now,
  finished_at: now,
  created_at: now,
  updated_at: now,
  warnings: [],
  failure_summary: null,
  failure_details: {},
  artifacts: [],
  log_url: null,
  events_url: null,
  cancel_url: null,
  results_url: null,
  manifest_url: null,
};

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

function stubApi() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://127.0.0.1");
      if (url.pathname.endsWith("/artifacts")) {
        return jsonResponse({
          items: [],
          pagination: {
            page: 1,
            page_size: 100,
            total: 0,
            has_next: false,
            has_previous: false,
          },
        });
      }
      if (/\/results\//.test(url.pathname)) {
        return jsonResponse({
          available: false,
          data: null,
          source_artifacts: [],
          warnings: [],
          availability: {},
          provenance: null,
          content_hash: null,
        });
      }
      if (url.pathname.endsWith("/api/v1/runs/run-1")) {
        return jsonResponse(managedRun);
      }
      return jsonResponse(
        {
          code: "NOT_FOUND",
          message: "not found",
          field_errors: [],
          details: {},
          request_id: "test",
        },
        { status: 404 },
      );
    }),
  );
}

function renderPage(initialEntry: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route
            element={<RunResultsPage forcedTab="network" />}
            path="/runs/:runId/network"
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("constrained result routes", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("keeps the run identity on screen for a managed run", async () => {
    stubApi();
    renderPage("/runs/run-1/network");

    // `GET /runs/{run_id}` returns a run resource, so the heading resolves from
    // the run name instead of rendering an empty manifest display name.
    expect(
      await screen.findByRole("heading", { name: "Bad Oeynhausen study area" }),
    ).toBeInTheDocument();
  });

  it("offers only the destinations that exist in the constrained route graph", async () => {
    stubApi();
    renderPage("/runs/run-1/network");

    await screen.findByRole("heading", { name: "Bad Oeynhausen study area" });
    const navigation = screen.getByRole("navigation", {
      name: "Result navigation",
    });
    const links = Array.from(navigation.querySelectorAll("a")).map(
      (link) => `${link.textContent}: ${link.getAttribute("href")}`,
    );

    expect(links).toEqual([
      "Run overview: /runs/run-1",
      "Network details: /runs/run-1/network",
    ]);
    await waitFor(() => {
      expect(
        screen.getByRole("link", { name: "Run workspace" }),
      ).toHaveAttribute("href", "/runs/run-1");
    });
    // Inputs and downloads is a secondary option, not a third result mode.
    fireEvent.click(
      screen.getByRole("button", { name: "More result options" }),
    );
    expect(screen.getByRole("menu")).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: "Inputs & downloads" }),
    ).toHaveAttribute("href", "/runs/run-1/files");
    // The legacy seven-tab strip has five tabs without a target route.
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
  });
});
