import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { RunResource } from "../../api/workflow";
import { RunPage } from "./RunPage";

const run = (overrides: Partial<RunResource> = {}): RunResource => ({
  id: "run-1",
  scenario_id: "scenario-1",
  scenario_revision_id: "revision-1",
  preview_id: null,
  name: "Bad Oeynhausen study area",
  description: null,
  output_label: null,
  status: "running",
  stage: "assess_heat_resources",
  progress: {
    stage: "assess_heat_resources",
    completed: 2,
    total: 6,
    fraction: null,
  },
  candidate_progress: null,
  configuration_snapshot: {},
  configuration_version: "default-v1",
  bbox: [7.1, 51.2, 7.2, 51.3],
  data_snapshot: {},
  application_version: "0.1.0",
  solver_name: null,
  solver_version: null,
  process_identity: {
    pid: 42,
    started_at: "2026-01-01T10:00:00Z",
    heartbeat_at: "2026-01-01T10:00:30Z",
  },
  started_at: "2026-01-01T10:00:00Z",
  finished_at: null,
  created_at: "2026-01-01T10:00:00Z",
  updated_at: "2026-01-01T10:00:30Z",
  warnings: [],
  failure_summary: null,
  failure_details: {},
  artifacts: [],
  log_url: null,
  events_url: "/api/v1/runs/run-1/events",
  cancel_url: "/api/v1/runs/run-1/cancel",
  results_url: null,
  manifest_url: null,
  ...overrides,
});

const summaryResult = {
  available: true,
  data: {
    total_heat_demand_mwh: 20,
    connected_heat_demand_mwh: 12,
    connected_share_pct: 60,
    connected_buildings: 2,
    total_annualized_eur: 2000,
    total_network_length_m: 100,
    peak_load_kw: 4,
  },
  source_artifacts: [],
  warnings: [],
  availability: {},
  provenance: null,
  content_hash: null,
};

const unavailableNetwork = {
  available: false,
  data: null,
  source_artifacts: [],
  warnings: [],
  availability: {},
  provenance: null,
  content_hash: null,
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type RouteReply =
  | { body: unknown; status?: number }
  | ((url: URL, init?: RequestInit) => { body: unknown; status?: number });

/**
 * Route every API call to a typed reply. An unknown call fails loudly so a
 * test cannot pass because a request silently never happened.
 */
function stubApi(routes: Record<string, RouteReply>) {
  const seen: string[] = [];
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://127.0.0.1");
      seen.push(`${init?.method ?? "GET"} ${url.pathname}${url.search}`);
      const route = routes[url.pathname];
      if (route === undefined) {
        return jsonResponse(
          {
            code: "UNEXPECTED_REQUEST",
            message: `${init?.method ?? "GET"} ${url.pathname}`,
            field_errors: [],
            details: {},
            request_id: "test",
          },
          404,
        );
      }
      const reply = typeof route === "function" ? route(url, init) : route;
      return jsonResponse(reply.body, reply.status ?? 200);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, seen };
}

function renderWorkspace(initialEntry = "/runs/run-1") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route element={<RunPage />} path="/runs/:runId" />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("unified run workspace", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the real stage, elapsed time, and worker state while running", async () => {
    stubApi({
      "/api/v1/runs/run-1": { body: run() },
      "/api/v1/runs/run-1/events": { body: [] },
      "/api/v1/runs/run-1/logs": {
        body: {
          run_id: "run-1",
          available: false,
          content: "",
          truncated: false,
        },
      },
    });

    renderWorkspace();

    expect(
      await screen.findByRole("heading", { name: /Bad Oeynhausen/ }),
    ).toBeInTheDocument();
    // The backend stage, not a fabricated percentage.
    expect(
      screen.getByRole("heading", { name: "Finding candidates" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "The backend cannot quantify this stage, so no percentage is shown.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/elapsed$/)).toBeInTheDocument();
    expect(screen.getAllByText(/^Worker/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Run run-1/)).toBeInTheDocument();
    // The selected area stays as geographic context for the whole run.
    expect(screen.getByText(/^Study area · /)).toHaveTextContent(
      "7.1, 51.2, 7.2, 51.3",
    );
  });

  it("keeps the run workspace when the event stream is interrupted", async () => {
    const { seen } = stubApi({
      "/api/v1/runs/run-1": { body: run() },
      "/api/v1/runs/run-1/events": { body: [] },
      "/api/v1/runs/run-1/logs": {
        body: {
          run_id: "run-1",
          available: false,
          content: "",
          truncated: false,
        },
      },
    });

    renderWorkspace();

    expect(
      await screen.findByRole("heading", { name: "Finding candidates" }),
    ).toBeInTheDocument();
    // Polling the authoritative run resource keeps the workspace recoverable.
    await waitFor(() => {
      expect(
        seen.filter((entry) => entry === "GET /api/v1/runs/run-1").length,
      ).toBeGreaterThan(0);
    });
  });

  it("transitions to the result summary in place on completion", async () => {
    stubApi({
      "/api/v1/runs/run-1": {
        body: run({
          status: "completed",
          stage: "complete",
          started_at: "2026-01-01T10:00:00Z",
          finished_at: "2026-01-01T10:04:00Z",
          process_identity: null,
          results_url: "/runs/run-1/results/overview",
        }),
      },
      "/api/v1/runs/run-1/results/summary": { body: summaryResult },
      "/api/v1/runs/run-1/results/network": { body: unavailableNetwork },
    });

    renderWorkspace();

    expect(await screen.findByText("12.0 MWh/a")).toBeInTheDocument();
    expect(screen.getByText("2 000 €/a")).toBeInTheDocument();
    // No percentage bar survives into the completed state.
    expect(screen.queryByLabelText("Run progress")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Network details" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Key results" }),
    ).toBeInTheDocument();
    for (const link of screen.getAllByRole("link", {
      name: "Inputs & downloads",
    })) {
      expect(link).toHaveAttribute("href", "/runs/run-1/files");
    }
  });

  it("keeps every disclosure identifier unique", async () => {
    stubApi({
      "/api/v1/runs/run-1": { body: run() },
      "/api/v1/runs/run-1/events": { body: [] },
    });

    renderWorkspace();

    const user = userEvent.setup();
    await user.click(await screen.findByText("Activity and diagnostics"));
    // The accordion region MUI renders for `aria-controls` already owns the
    // id, so `AccordionDetails` must not declare it a second time.
    expect(document.querySelectorAll("#run-activity-content")).toHaveLength(1);
    expect(document.querySelectorAll("#run-failure-diagnostics")).toHaveLength(
      0,
    );
  });

  it("translates the calculation lifecycle events into the activity feed", async () => {
    stubApi({
      "/api/v1/runs/run-1": { body: run() },
      "/api/v1/runs/run-1/events": {
        body: [
          {
            id: "event-1",
            run_id: "run-1",
            job_kind: "run",
            sequence: 1,
            event_type: "calculation.stage_started",
            data: { stage: "preparing_area" },
            occurred_at: "2026-01-01T10:00:00Z",
          },
        ],
      },
    });

    const user = userEvent.setup();
    renderWorkspace();

    await user.click(await screen.findByText("Activity and diagnostics"));

    // An internal event name must never reach the reader as-is.
    expect(
      await screen.findByText("Started preparing area."),
    ).toBeInTheDocument();
    expect(screen.queryByText("calculation.stage_started")).toBeNull();
  });

  it("explains a failure inside the workspace and keeps the run context", async () => {
    stubApi({
      "/api/v1/runs/run-1": {
        body: run({
          status: "failed",
          stage: "optimize_heat_grid",
          finished_at: "2026-01-01T10:02:00Z",
          failure_summary: "The calculation worker could not be started.",
          failure_details: {
            code: "CALCULATION_WORKER_UNAVAILABLE",
            issues: [
              {
                message: "No solver is available.",
                remediation: "Install the solver.",
              },
            ],
          },
        }),
      },
      "/api/v1/runs/run-1/events": { body: [] },
    });

    renderWorkspace();

    expect(
      await screen.findByText("This calculation did not finish"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("The calculation worker could not be started."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No solver is available. Install the solver."),
    ).toBeInTheDocument();
    expect(screen.getByText(/Run run-1/)).toBeInTheDocument();
    // Retry means a new immutable run for the same rectangle.
    expect(
      screen.getByRole("link", {
        name: "Start a new calculation with this area",
      }),
    ).toHaveAttribute("href", "/?bbox=7.1%2C51.2%2C7.2%2C51.3");
  });

  it("distinguishes a cancelled run from a failure", async () => {
    stubApi({
      "/api/v1/runs/run-1": {
        body: run({ status: "cancelled", stage: "optimizing_network" }),
      },
      "/api/v1/runs/run-1/events": { body: [] },
    });

    renderWorkspace();

    expect(
      await screen.findByText("This calculation was cancelled"),
    ).toBeInTheDocument();
  });

  it("requests cancellation only after an explicit confirmation", async () => {
    const user = userEvent.setup();
    const { fetchMock } = stubApi({
      "/api/v1/runs/run-1": { body: run() },
      "/api/v1/runs/run-1/cancel": (_url, init) => ({
        body:
          init?.method === "POST"
            ? run({ status: "cancellation_requested" })
            : run(),
      }),
      "/api/v1/runs/run-1/events": { body: [] },
    });

    renderWorkspace();

    await screen.findByRole("heading", { name: "Finding candidates" });
    await user.click(screen.getByRole("button", { name: "Cancel run" }));

    const cancelCalls = fetchMock.mock.calls.filter(
      (call) => (call[1] as RequestInit | undefined)?.method === "POST",
    );
    expect(cancelCalls).toHaveLength(0);

    await user.click(
      screen.getByRole("button", { name: "Confirm cancellation" }),
    );
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          (call) =>
            (call[1] as RequestInit | undefined)?.method === "POST" &&
            String(call[0]).includes("/api/v1/runs/run-1/cancel"),
        ),
      ).toBe(true);
    });
  });

  it("explains an unknown run identifier instead of showing a blank page", async () => {
    stubApi({
      "/api/v1/runs/run-1": {
        status: 404,
        body: {
          code: "NOT_FOUND",
          message: "Run was not found.",
          field_errors: [],
          details: {},
          request_id: "test",
        },
      },
    });

    renderWorkspace();

    expect(
      await screen.findByText("This run could not be found"),
    ).toBeInTheDocument();
    expect(screen.getByText("Requested run: run-1")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Select a study area" }),
    ).toHaveAttribute("href", "/");
    expect(
      screen.getByRole("link", { name: "Recent runs" }),
    ).toBeInTheDocument();
  });

  it("contains a run-record failure instead of replacing the workspace", async () => {
    const user = userEvent.setup();
    stubApi({
      "/api/v1/runs/run-1": {
        status: 400,
        body: {
          code: "RUN_RECORD_UNAVAILABLE",
          message: "Run record could not be restored.",
          field_errors: [],
          details: {},
          request_id: "test",
        },
      },
    });

    renderWorkspace();

    expect(
      await screen.findByText("Run record could not be restored."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(
      screen.getByText("Run record could not be restored."),
    ).toBeInTheDocument();
  });
});
