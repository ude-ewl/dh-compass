import { test, expect } from "@playwright/test";

const run = {
  id: "demo/run-1",
  scenario: "demo",
  timestamp: "run-1",
  display_name: "demo — run-1",
  name: "demo — run-1",
  status: "completed",
  source: "legacy_output",
  legacy: true,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
  summary: {
    total_heat_demand_mwh: 20,
    connected_heat_demand_mwh: 12,
    disconnected_heat_demand_mwh: 8,
    connected_share_pct: 60,
    connected_buildings: 2,
    total_annualized_eur: 2000,
    total_network_length_m: 100,
    peak_load_kw: 4,
  },
  artifacts: [
    {
      id: "full_results.json",
      display_name: "Full results",
      kind: "results",
      media_type: "application/json",
      status: "available",
      available: true,
      byte_size: 10,
      checksum_sha256: null,
      error: null,
      download_url:
        "/api/v1/runs/demo%2Frun-1/artifacts/full_results.json/download",
    },
  ],
  warnings: [],
};

const candidate = {
  id: 7,
  decision: "connected",
  is_connected: true,
  annual_heat_demand_mwh: 12,
  buildings: 2,
  peak_load_kw: 4,
  total_network_length_m: 100,
  avg_lhd: 2.5,
  central_cost: 2000,
  decentral_cost: 2100,
};

const rejectedCandidate = {
  ...candidate,
  id: 8,
  decision: "rejected",
  is_connected: false,
  central_cost: 2500,
  decentral_cost: 1900,
};

const candidateNetwork = {
  type: "FeatureCollection",
  features: [7, 8].map((candidateId) => ({
    type: "Feature" as const,
    geometry: {
      type: "LineString",
      coordinates: [
        [7 + (candidateId - 7) / 10, 51],
        [7.05 + (candidateId - 7) / 10, 51.05],
      ],
    },
    properties: {
      candidate_id: candidateId,
      decision: candidateId === 7 ? "connected" : "rejected",
    },
  })),
};

function envelope(data: unknown) {
  return { available: true, data, source_artifacts: [], warnings: [] };
}

test("opens an existing run and shows final combined results", async ({
  page,
}, testInfo) => {
  await page.route("**/api/v1/health", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        service: "dh-compass-api",
        version: "0.1.0",
        request_id: "e2e",
      }),
    });
  });
  await page.route("**/api/v1/runs?**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/runs")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          items: [run],
          pagination: {
            page: 1,
            page_size: 50,
            total: 1,
            has_next: false,
            has_previous: false,
          },
        }),
      });
      return;
    }
    await route.continue();
  });
  await page.route("**/api/v1/runs/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.endsWith("/runs/recent")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          items: [run],
          pagination: {
            page: 1,
            page_size: 50,
            total: 1,
            has_next: false,
            has_previous: false,
          },
        }),
      });
    }
    if (pathname.endsWith("/results/summary"))
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(envelope(run.summary)),
      });
    if (pathname.endsWith("/results/network")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          envelope({
            final_network: { type: "FeatureCollection", features: [] },
            candidate_network: candidateNetwork,
            lhd: null,
            connection_paths: { type: "FeatureCollection", features: [] },
            availability: {
              final_network: true,
              candidate_network: false,
              lhd: false,
              connection_paths: false,
            },
          }),
        ),
      });
    }
    if (pathname.endsWith("/results/candidates"))
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(envelope([candidate, rejectedCandidate])),
      });
    if (pathname.endsWith("/results/supply"))
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          envelope({ supply: {}, storage: {}, total_heat_production_mwh: 12 }),
        ),
      });
    if (pathname.endsWith("/results/costs"))
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          envelope({
            total_annualized_eur: 2000,
            supply_annualized_eur: 1400,
            grid_annualized_eur: 600,
          }),
        ),
      });
    if (pathname.endsWith("/artifacts"))
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          items: run.artifacts,
          pagination: {
            page: 1,
            page_size: 200,
            total: 1,
            has_next: false,
            has_previous: false,
          },
        }),
      });
    if (pathname.endsWith("/results/iterations"))
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          envelope([
            {
              step: 0,
              subgraph_id: 7,
              decision: "connected",
              central_cost_total: 2000,
              marginal_central_cost: 2000,
              decentral_cost: 2100,
              cumulative_connected_ids: [7],
            },
            {
              step: 1,
              subgraph_id: 8,
              decision: "rejected",
              central_cost_total: 2000,
              marginal_central_cost: 500,
              decentral_cost: 1900,
              cumulative_connected_ids: [7],
            },
          ]),
        ),
      });
    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(run),
    });
  });

  await page.goto("/recent");
  await expect(
    page.getByRole("heading", { name: "Recent runs" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Open" }).click();
  await expect(
    page.getByRole("heading", { name: "demo — run-1" }),
  ).toBeVisible();
  await expect(page.getByText("Annual demand", { exact: true })).toBeVisible();
  await expect(page.getByText("12.0 MWh/a", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("complementary", { name: "Final combined grid results" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Network details" })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("link", { name: "Inputs & downloads" }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("result-workspace-baseline.png"),
    fullPage: true,
  });
});
