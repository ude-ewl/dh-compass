import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { InputsAndDownloads } from "./InputsAndDownloads";

const managedRun = {
  id: "run-1",
  scenario_id: "scenario-1",
  scenario_revision_id: "revision-1",
  preview_id: null,
  name: "Study area",
  description: null,
  output_label: null,
  status: "completed",
  stage: "complete",
  progress: null,
  candidate_progress: null,
  configuration_snapshot: {},
  configuration_version: "default-v1",
  bbox: null,
  data_snapshot: {},
  application_version: "0.1.0",
  solver_name: null,
  solver_version: null,
  process_identity: null,
  started_at: null,
  finished_at: null,
  created_at: "2026-01-01T10:00:00Z",
  updated_at: "2026-01-01T10:00:00Z",
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

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
  });
}

describe("InputsAndDownloads", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("offers downloads for managed artifacts, whose API records omit available", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input), "http://127.0.0.1");
        if (url.pathname.endsWith("/artifacts")) {
          return jsonResponse({
            items: [
              {
                id: "full_results.json",
                display_name: "Full results",
                description: null,
                media_type: "application/json",
                byte_size: 100,
                status: "available",
                checksum_sha256: null,
                download_url:
                  "/api/v1/runs/run-1/artifacts/full_results.json/download",
              },
            ],
            pagination: {
              page: 1,
              page_size: 100,
              total: 1,
              has_next: false,
              has_previous: false,
            },
          });
        }
        if (url.pathname.endsWith("/results/summary")) {
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
        if (url.pathname.endsWith("/runs/run-1")) {
          return jsonResponse(managedRun);
        }
        throw new Error(`Unexpected request: ${url.pathname}`);
      }),
    );

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <InputsAndDownloads runId="run-1" />
      </QueryClientProvider>,
    );

    expect(
      await screen.findByRole("link", { name: "Download" }),
    ).toHaveAttribute(
      "href",
      "/api/v1/runs/run-1/artifacts/full_results.json/download",
    );
    expect(screen.queryByText("Export results")).not.toBeInTheDocument();
  });
});
