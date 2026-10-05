import { expect, test } from "@playwright/test";

test("completed grid shows only combined results and charts at desktop and mobile widths", async ({
  page,
}, testInfo) => {
  const envelope = (data: unknown) => ({
    available: true,
    data,
    warnings: [],
    source_artifacts: [],
    availability: {},
    provenance: null,
    content_hash: null,
  });
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const sections: Record<string, unknown> = {
      summary: {
        connected_heat_demand_mwh: 1500,
        peak_load_kw: 620,
        connected_buildings: 135,
        final_connection_length_m: 3000,
        average_linear_heat_density_mwh_per_m_a: 0.5,
        total_annualized_eur: 103000,
      },
      network: {
        candidate_network: { type: "FeatureCollection", features: [] },
        connection_paths: { type: "FeatureCollection", features: [] },
      },
      iterations: [],
      candidates: [],
      costs: {
        grid_breakdown: {
          distribution_pipes_eur: 15000,
          connection_pipelines_eur: 5000,
          building_connections_eur: 8000,
          transfer_stations_eur: 5000,
          pumps_eur: 2000,
        },
        supply_breakdown: {
          investment: { total_eur: 25000 },
          fixed_om: { total_eur: 13000 },
          operational: { net_operational_annual_eur: 30000 },
        },
      },
      supply: {
        supply: {
          river_heat_pump: { capacity_kw: 400, annual_energy_mwh: 1200 },
          boiler: { capacity_kw: 220, annual_energy_mwh: 300 },
        },
        resources: {
          river_heat_pump: { used: 400, limit: 800, unit: "kW" },
          geothermal: { used: 0, limit: 100, unit: "kW" },
        },
      },
    };
    const section = path.split("/").at(-1)!;
    await route.fulfill({
      json: path.includes("/results/")
        ? envelope(sections[section])
        : {
            id: "final-run",
            name: "Combined grid study",
            status: "completed",
            stage: "complete",
            bbox: [8.785, 52.199, 8.822, 52.221],
            started_at: "2026-10-04T10:00:00Z",
            finished_at: "2026-10-04T10:04:00Z",
            artifacts: [],
            warnings: [],
          },
    });
  });
  await page.goto("/runs/final-run");
  await expect(
    page.getByRole("heading", { name: "Key results" }),
  ).toBeVisible();
  await expect(page.getByLabel("Subgraph details")).toHaveCount(0);
  await expect(page.getByLabel("Grid statistics")).toHaveCount(0);
  const sidebar = page.getByLabel("Final combined grid results");
  await expect(sidebar.getByRole("button", { name: "View data" })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("link", { name: "New run", exact: true }),
  ).toBeVisible();
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const costChart = page.getByRole("img", {
      name: "Annualized cost breakdown chart; values listed below",
    });
    await costChart.scrollIntoViewIfNeeded();
    const bounds = (await costChart.boundingBox())!;
    for (const [index, label] of ["Infrastructure", "Supply"].entries()) {
      await page.mouse.move(
        bounds.x + 70 + (bounds.width - 86) * (index === 0 ? 0.25 : 0.75),
        bounds.y + 180,
      );
      const tooltip = page.getByRole("tooltip");
      await expect(tooltip).toBeVisible();
      await expect(tooltip.getByText(label, { exact: true })).toBeVisible();
      await expect(tooltip).toContainText(
        index === 0 ? "Building connections" : "Investment",
      );
      await expect(tooltip).not.toContainText(
        index === 0 ? "Investment" : "Building connections",
      );
      const tooltipBounds = (await tooltip.boundingBox())!;
      expect(tooltipBounds.x).toBeGreaterThanOrEqual(0);
      expect(tooltipBounds.x + tooltipBounds.width).toBeLessThanOrEqual(width);
      expect(tooltipBounds.y).toBeGreaterThanOrEqual(0);
      expect(tooltipBounds.y + tooltipBounds.height).toBeLessThanOrEqual(900);
    }
    await page.mouse.move(0, 0);
    for (const title of [
      "Annualized cost breakdown",
      "Installed capacities",
      "Generation mix",
      "Location-dependent potential used",
    ]) {
      const heading = sidebar.getByRole("heading", { name: title });
      await heading.scrollIntoViewIfNeeded();
      await expect(heading).toBeVisible();
    }
    await expect(
      sidebar.getByText("River heat pump · 50.0% used"),
    ).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await sidebar.evaluate((element) => {
      element.scrollTop = 0;
    });
    await page.screenshot({
      path: testInfo.outputPath(`combined-grid-${width}.png`),
      fullPage: true,
    });
  }
});
