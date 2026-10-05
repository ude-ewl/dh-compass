import { expect, test } from "@playwright/test";

const now = "2026-01-01T00:00:00Z";
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

const project = {
  id: "project-1",
  name: "Planning project",
  description: null,
  archived: false,
  scenario_count: 0,
  recent_run_statuses: [],
  created_at: now,
  updated_at: now,
};

const document = {
  network: { linear_heat_density_threshold: 25 },
};

const scenario = {
  id: "scenario-1",
  project_id: project.id,
  name: "Planning scenario",
  description: null,
  archived: false,
  current_revision_id: "revision-1",
  revision_number: 1,
  readiness_state: "incomplete",
  preview_id: null,
  preview_stale_reason: null,
  run_required: false,
  area_summary: {},
  effective_lhd_threshold: 25,
  expert_override_count: 0,
  created_at: now,
  updated_at: now,
  revision: {
    id: "revision-1",
    scenario_id: "scenario-1",
    parent_revision_id: null,
    revision_number: 1,
    document,
    created_at: now,
  },
};

test("creates a project and a default scenario", async ({
  page: browserPage,
}) => {
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

    if (url.pathname === "/api/v1/health") {
      return json({
        status: "ok",
        service: "dh-compass-api",
        version: "0.1.0",
        request_id: "project-flow",
      });
    }
    if (url.pathname === "/api/v1/projects" && method === "GET")
      return json(page([]));
    if (url.pathname === "/api/v1/projects" && method === "POST")
      return json(project, 201);
    if (url.pathname === "/api/v1/projects/project-1" && method === "GET") {
      return json({ ...project, scenarios: [] });
    }
    if (url.pathname === "/api/v1/projects/project-1/runs")
      return json(page([]));
    if (
      url.pathname === "/api/v1/projects/project-1/scenarios" &&
      method === "POST"
    ) {
      return json(scenario, 201);
    }
    if (url.pathname === "/api/v1/scenarios/scenario-1") return json(scenario);
    if (url.pathname === "/api/v1/scenarios/scenario-1/config") {
      return json({
        scenario_id: scenario.id,
        revision_id: "revision-1",
        revision_number: 1,
        document,
        effective_document: document,
        created_at: now,
      });
    }
    if (url.pathname === "/api/v1/scenarios/scenario-1/runs")
      return json(page([]));
    if (url.pathname === "/api/v1/configuration/schema") {
      return json({
        version: "1",
        fields: [
          {
            key: "network.linear_heat_density_threshold",
            section: "network",
            section_label: "Network and infrastructure",
            label: "Linear heat density threshold",
            description: "Minimum annual heat demand per metre of network.",
            data_type: "number",
            unit: "MWh/(m·a)",
            default: 25,
            value: 25,
            expert_only: false,
            impact: "preview",
            preprocessing_impact: false,
            sensitive: false,
            path_policy: null,
            constraints: { minimum: 0 },
          },
        ],
      });
    }
    return json(
      {
        code: "UNEXPECTED_REQUEST",
        message: `${method} ${url.pathname}`,
        field_errors: [],
        details: {},
        request_id: "project-flow",
      },
      404,
    );
  });

  await browserPage.goto("/projects");
  await browserPage
    .getByRole("button", { name: "Create first project" })
    .click();
  await browserPage.getByLabel("Project name").fill(project.name);
  await browserPage
    .getByRole("button", { name: "Create", exact: true })
    .click();

  await browserPage.waitForURL("**/projects/project-1");
  await browserPage.getByRole("button", { name: "New scenario" }).click();
  await browserPage.getByLabel("Scenario name").fill(scenario.name);
  await browserPage
    .getByRole("button", { name: "Create", exact: true })
    .click();

  await expect(
    browserPage.getByRole("heading", { name: scenario.name }),
  ).toBeVisible();
  await expect(browserPage.getByLabel("Scenario steps")).toBeVisible();
});
