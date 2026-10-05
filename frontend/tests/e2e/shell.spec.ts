import { test, expect } from "@playwright/test";

test("opens the constrained application shell by default", async ({ page }) => {
  await page.route("**/api/v1/calculations/contract", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        bbox: {
          coverage_bbox: [5.8, 50.2, 9.5, 52.6],
          min_area_km2: 0.01,
          max_area_km2: 1000,
        },
      }),
    });
  });

  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Select a study area" }),
  ).toBeAttached();
  await expect(page.getByRole("link", { name: "Recent runs" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Help" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Draw new area" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Projects" })).toHaveCount(0);
  await expect(page.getByText("API connected")).toHaveCount(0);
});
