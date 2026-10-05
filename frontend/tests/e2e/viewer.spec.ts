import { expect, test, type Page } from "@playwright/test";

const edge = (id: number, coordinates: number[][]) => ({
  type: "Feature",
  geometry: { type: "LineString", coordinates },
  properties: { candidate_id: id, linear_heat_density: 2.3 },
});
const collection = (features: ReturnType<typeof edge>[]) => ({
  type: "FeatureCollection",
  features,
});
const network = collection([
  edge(1, [
    [8.793, 52.204],
    [8.793, 52.209],
    [8.799, 52.209],
    [8.799, 52.204],
  ]),
  edge(1, [
    [8.793, 52.207],
    [8.799, 52.207],
  ]),
  edge(2, [
    [8.805, 52.213],
    [8.811, 52.213],
    [8.811, 52.218],
  ]),
  edge(3, [
    [8.808, 52.202],
    [8.808, 52.207],
    [8.814, 52.207],
    [8.814, 52.202],
  ]),
]);
const run = {
  id: "viewer-run",
  name: "Bad Oeynhausen",
  status: "running",
  stage: "optimize_heat_grid",
  bbox: [8.785, 52.199, 8.822, 52.221],
  created_at: "2026-10-04T10:00:00Z",
  started_at: "2026-10-04T10:00:00Z",
  updated_at: "2026-10-04T10:02:00Z",
  finished_at: null,
  process_identity: { pid: 42, heartbeat_at: new Date().toISOString() },
  progress: { stage: "optimize_heat_grid", fraction: null },
  warnings: [],
  artifacts: [],
  failure_details: {},
  candidate_progress: {
    completed_candidates: 3,
    total_candidates: 3,
    connected_candidates: 2,
    rejected_candidates: 1,
  },
};
const event = (
  sequence: number,
  event_type: string,
  data: Record<string, unknown>,
) => ({
  id: `event-${sequence}`,
  run_id: run.id,
  job_kind: "run",
  sequence,
  event_type,
  data,
  occurred_at: run.updated_at,
});
const events = [
  event(1, "optimization.candidate_started", {
    candidate_id: 1,
    candidate_network_geojson: network,
  }),
  event(2, "optimization.candidate_completed", {
    candidate_id: 1,
    decision: "connected",
    annual_heat_demand_mwh: 900,
    buildings: 82,
    marginal_central_cost: 65000,
    decentral_cost: 87000,
    central_cost_total: 65000,
    connected_heat_demand_mwh: 900,
  }),
  event(3, "optimization.candidate_started", { candidate_id: 2 }),
  event(4, "optimization.candidate_completed", {
    candidate_id: 2,
    decision: "rejected",
    marginal_central_cost: 42000,
    decentral_cost: 31000,
    central_cost_total: 65000,
    connected_heat_demand_mwh: 900,
  }),
  event(5, "optimization.candidate_started", { candidate_id: 3 }),
  event(6, "optimization.candidate_completed", {
    candidate_id: 3,
    decision: "connected",
    annual_heat_demand_mwh: 600,
    buildings: 53,
    marginal_central_cost: 38000,
    decentral_cost: 55000,
    central_cost_total: 103000,
    connected_heat_demand_mwh: 1500,
    connecting_path_geojson: collection([
      edge(3, [
        [8.799, 52.207],
        [8.804, 52.207],
        [8.808, 52.207],
      ]),
    ]),
  }),
];

async function mockRun(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/events")) {
      if (url.searchParams.get("format") === "json") {
        return route.fulfill({ json: events.slice(0, 3) });
      }
      return route.fulfill({
        contentType: "text/event-stream",
        body: events
          .slice(3)
          .map(
            (item) =>
              `id: ${item.sequence}\nevent: ${item.event_type}\ndata: ${JSON.stringify(item)}\n\n`,
          )
          .join(""),
      });
    }
    return route.fulfill({ json: run });
  });
}

async function settleMap(page: Page) {
  await page.waitForFunction(
    () => {
      const map = document.querySelector('[data-testid="maplibre-map"]');
      return (
        (map && getComputedStyle(map).opacity === "1") ||
        [...document.querySelectorAll("button")].some((button) =>
          button.textContent?.includes("Retry map"),
        )
      );
    },
    undefined,
    { timeout: 15000 },
  );
}

test("classic viewer follows streamed grid growth and allows history playback", async ({
  page,
}, testInfo) => {
  await mockRun(page);
  await page.goto("/runs/viewer-run");
  await expect(page.getByText("Step 6 / 6")).toBeVisible();
  await expect(page.getByLabel("Grid statistics")).toContainText(
    "Connected: 2",
  );
  await expect(page.getByLabel("Grid statistics")).toContainText("Rejected: 1");
  await expect(page.getByLabel("Grid statistics")).toContainText("103 000 €/a");
  await expect(
    page.getByRole("heading", { name: "Candidate #3" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "First step" }).click();
  await expect(page.getByText("Evaluating subgraph #1…")).toBeVisible();
  await expect(page.getByLabel("Grid statistics")).toContainText(
    "Connected: 0",
  );
  await expect(page.getByRole("button", { name: "Follow live" })).toHaveCount(0);
  await expect(
    page.getByText(/Live grid|provisional|Viewing history/),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Last step" }).click();
  await expect(page.getByText("Step 6 / 6")).toBeVisible();
  for (const name of ["LHD", "Edges", "Paths"]) {
    await expect(page.getByRole("button", { name, exact: true })).toHaveCount(0);
  }
  await page.getByRole("button", { name: "Center map", exact: true }).click();
  await settleMap(page);
  await page.screenshot({
    path: testInfo.outputPath("classic-viewer-desktop.png"),
  });
});

test("viewer and area controls remain usable on mobile without horizontal overflow", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockRun(page);
  await page.goto("/runs/viewer-run");
  await expect(page.getByText("Step 6 / 6")).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await settleMap(page);
  await page.screenshot({
    path: testInfo.outputPath("classic-viewer-mobile.png"),
    fullPage: true,
  });
  await page.route("**/api/v1/calculations/contract", (route) =>
    route.fulfill({
      json: {
        bbox: {
          coverage_bbox: [5.8, 50.2, 9.5, 52.6],
          min_area_km2: 0.01,
          max_area_km2: 1000,
        },
      },
    }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Draw new area" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await settleMap(page);
  await page.screenshot({
    path: testInfo.outputPath("classic-area-mobile.png"),
    fullPage: true,
  });
});

test("all run stages stay inside the progress panel at narrow and desktop widths", async ({
  page,
}) => {
  await mockRun(page);
  await page.goto("/runs/viewer-run");
  const stages = page.getByLabel("Run stages");
  const panel = page.getByRole("region", { name: "Run progress details" });
  await expect(stages.getByText("Complete", { exact: true })).toBeVisible();
  for (const width of [615, 900, 1280]) {
    await page.setViewportSize({ width, height: 524 });
    const bounds = await panel.boundingBox();
    const chips = stages.locator(".MuiChip-root");
    await expect(chips).toHaveCount(6);
    for (const chip of await chips.all()) {
      const rect = await chip.boundingBox();
      expect(rect!.x).toBeGreaterThanOrEqual(bounds!.x);
      expect(rect!.x + rect!.width).toBeLessThanOrEqual(
        bounds!.x + bounds!.width,
      );
      expect(rect!.y + rect!.height).toBeLessThanOrEqual(
        bounds!.y + bounds!.height,
      );
    }
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
  }
});

test("area selection uses the viewer's map and side panel", async ({
  page,
}, testInfo) => {
  await page.route("**/api/v1/calculations/contract", (route) =>
    route.fulfill({
      json: {
        bbox: {
          coverage_bbox: [5.8, 50.2, 9.5, 52.6],
          min_area_km2: 0.01,
          max_area_km2: 1000,
        },
      },
    }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Study area", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Start calculation" }),
  ).toBeDisabled();
  const map = await page
    .getByRole("region", { name: "Study area map", exact: true })
    .boundingBox();
  const sidebar = await page.getByLabel("Study area controls").boundingBox();
  expect(map!.width).toBeGreaterThan(sidebar!.width);
  expect(sidebar!.x).toBeGreaterThanOrEqual(map!.x + map!.width - 1);
  await settleMap(page);
  await page.screenshot({
    path: testInfo.outputPath("classic-area-desktop.png"),
  });
});
