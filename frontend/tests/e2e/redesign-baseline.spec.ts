import { expect, test } from "@playwright/test";

const now = "2026-01-01T00:00:00Z";
const bbox: [number, number, number, number] = [7.1, 51.2, 7.2, 51.3];

const page = <T>(items: T[]) => ({
  items,
  pagination: {
    page: 1,
    page_size: 50,
    total: items.length,
    has_next: false,
    has_previous: false,
  },
});

const scenario = {
  id: "scenario-1",
  project_id: "project-1",
  name: "Baseline scenario",
  description: null,
  archived: false,
  current_revision_id: "revision-1",
  revision_number: 1,
  readiness_state: "incomplete",
  preview_id: null,
  preview_stale_reason: null,
  run_required: false,
  area_summary: { execution_bbox: bbox },
  effective_lhd_threshold: 2,
  expert_override_count: 0,
  created_at: now,
  updated_at: now,
};

const document = {
  scenario: { bbox },
  network: { linear_heat_density_threshold: 2 },
};

function health() {
  return {
    status: "ok",
    service: "dh-compass-api",
    version: "0.1.0",
    request_id: "baseline",
  };
}

test("captures the current bbox workspace baseline", async ({
  page: browserPage,
}, testInfo) => {
  await browserPage.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({
        contentType: "application/json",
        status,
        body: JSON.stringify(body),
      });

    if (url.pathname === "/api/v1/health") return json(health());
    if (url.pathname === "/api/v1/scenarios/scenario-1") return json(scenario);
    if (url.pathname === "/api/v1/scenarios/scenario-1/config")
      return json({
        scenario_id: scenario.id,
        revision_id: "revision-1",
        revision_number: 1,
        document,
        effective_document: document,
        created_at: now,
      });
    if (url.pathname === "/api/v1/configuration/schema")
      return json({ version: "1", fields: [] });
    if (url.pathname === "/api/v1/scenarios/scenario-1/runs")
      return json(page([]));
    if (url.pathname === "/api/v1/scenarios/scenario-1/area") {
      if (method === "PUT") {
        const submitted = request.postDataJSON() as {
          bbox: [number, number, number, number];
        };
        return json({
          scenario_id: scenario.id,
          revision_id: "revision-1",
          execution_bbox: submitted.bbox,
          display_geometry: null,
          source: "manual",
          imported_filename: null,
          crs: "EPSG:4326",
          validation_issues: [],
          updated_at: now,
        });
      }
      return json({
        scenario_id: scenario.id,
        revision_id: "revision-1",
        execution_bbox: bbox,
        display_geometry: null,
        source: "bbox",
        imported_filename: null,
        crs: "EPSG:4326",
        validation_issues: [],
        updated_at: now,
      });
    }
    return json(
      {
        code: "UNEXPECTED_REQUEST",
        message: `${method} ${url.pathname}`,
        field_errors: [],
        details: {},
        request_id: "baseline",
      },
      404,
    );
  });

  await browserPage.goto("/projects/project-1/scenarios/scenario-1/area");
  await expect(
    browserPage.getByRole("heading", { name: "Study area", exact: true }),
  ).toBeVisible();
  await expect(
    browserPage.getByRole("button", { name: "Draw a new bounding box" }),
  ).toBeVisible();
  const map = browserPage.getByTestId("maplibre-map");
  await expect(map).toHaveAttribute("aria-hidden", "false");
  const west = browserPage.getByLabel("West");
  const initialWest = await west.inputValue();
  await browserPage
    .getByRole("button", { name: "Draw a new bounding box" })
    .click();
  await expect(
    browserPage.getByText(
      "Drag from one corner of the study area to the opposite corner on the map.",
    ),
  ).toBeVisible();
  await map.scrollIntoViewIfNeeded();
  const mapBounds = await map.boundingBox();
  if (!mapBounds) throw new Error("The study-area map has no bounding box.");
  await browserPage.mouse.move(mapBounds.x + 120, mapBounds.y + 120);
  await browserPage.mouse.down();
  await browserPage.mouse.move(mapBounds.x + 300, mapBounds.y + 280, {
    steps: 10,
  });
  await browserPage.mouse.up();

  await expect(west).not.toHaveValue(initialWest);
  await expect(
    browserPage.getByRole("button", { name: "Draw a new bounding box" }),
  ).toBeVisible();
  const saveRequest = browserPage.waitForRequest(
    (request) =>
      request.method() === "PUT" &&
      new URL(request.url()).pathname === "/api/v1/scenarios/scenario-1/area",
  );
  await browserPage
    .getByRole("button", { name: "Save and validate area" })
    .click();
  const request = await saveRequest;
  expect((request.postDataJSON() as { bbox: number[] }).bbox).not.toEqual(bbox);
  await browserPage.screenshot({
    path: testInfo.outputPath("bbox-workspace-baseline.png"),
    fullPage: true,
  });
});

test("captures the current run monitor baseline", async ({
  page: browserPage,
}, testInfo) => {
  await browserPage.route("**/api/v1/health", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(health()),
    }),
  );
  await browserPage.route("**/api/v1/runs/run-1/events?**", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
  await browserPage.route("**/api/v1/runs/run-1", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "run-1",
        scenario_id: "scenario-1",
        scenario_revision_id: "revision-1",
        preview_id: "preview-1",
        name: "Baseline run",
        description: null,
        output_label: null,
        status: "running",
        stage: "prepare_geospatial_data",
        progress: {
          stage: "prepare_geospatial_data",
          completed: 2,
          total: 6,
          fraction: null,
        },
        candidate_progress: null,
        configuration_snapshot: document,
        application_version: "0.1.0",
        solver_name: null,
        solver_version: null,
        process_identity: null,
        started_at: now,
        finished_at: null,
        created_at: now,
        updated_at: now,
        warnings: [],
        failure_summary: null,
        failure_details: {},
        artifacts: [],
        log_url: null,
        events_url: "/api/v1/runs/run-1/events",
        cancel_url: "/api/v1/runs/run-1/cancel",
        results_url: null,
        manifest_url: null,
      }),
    }),
  );

  await browserPage.goto("/runs/run-1/monitor");
  await expect(browserPage).toHaveURL(/\/runs\/run-1\/monitor$/);
  await expect(
    browserPage.getByRole("heading", { name: "Baseline run" }),
  ).toBeVisible();
  await expect(
    browserPage.getByText("Prepare geospatial data", { exact: true }).first(),
  ).toBeVisible();
  await browserPage.screenshot({
    path: testInfo.outputPath("run-monitor-baseline.png"),
    fullPage: true,
  });
});
