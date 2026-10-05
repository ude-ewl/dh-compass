import { test, expect } from "@playwright/test";

test("switches languages without losing the area, persists across reload and explains NRW scope", async ({
  page,
}) => {
  await page.route("**/api/v1/calculations/contract", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        bbox: {
          coverage_bbox: [5.866, 50.322, 9.531, 52.531],
          min_area_km2: 0.01,
          max_area_km2: 2500,
        },
      }),
    }),
  );
  let submitted: unknown;
  await page.route("**/api/v1/calculations", async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "TEST_UNAVAILABLE",
          message: "The API request could not be completed.",
          request_id: "locale-test",
        },
      }),
    });
  });
  await page.goto("/");
  await page.getByText("Exact extent", { exact: true }).click();
  const west = page.getByRole("spinbutton", { name: "West" });
  await west.fill("7.1");
  await page.getByRole("spinbutton", { name: "South" }).fill("51.2");
  await page.getByRole("spinbutton", { name: "East" }).fill("7.2");
  await page.getByRole("spinbutton", { name: "North" }).fill("51.3");
  await page.getByRole("combobox", { name: "Language / Sprache" }).click();
  await page.getByRole("option", { name: "Deutsch" }).click();
  await expect(
    page.getByRole("button", { name: "Berechnung starten" }),
  ).toBeEnabled();
  await expect(page.getByRole("spinbutton", { name: "Westen" })).toHaveValue(
    "7.1",
  );
  await expect(page.locator("html")).toHaveAttribute("lang", "de");
  await page.getByRole("button", { name: "Berechnung starten" }).click();
  await expect.poll(() => submitted).toEqual({ bbox: [7.1, 51.2, 7.2, 51.3] });
  await page.getByRole("link", { name: "Hilfe", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Über DH-COMPASS" }),
  ).toBeVisible();
  await expect(
    page.getByText(/Derzeit nur für Nordrhein-Westfalen/),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Konfigurationsanleitung" }),
  ).toHaveAttribute("href", /DH-COMPASS\/blob\/main\/docs\/configuration.md$/);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Über DH-COMPASS" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("combobox", { name: "Language / Sprache" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../outputs/polish/help-de-mobile.png",
    fullPage: true,
  });
  await page.getByRole("combobox", { name: "Language / Sprache" }).click();
  await page.getByRole("option", { name: "English" }).click();
  await expect(
    page.getByRole("heading", { name: "About DH-COMPASS" }),
  ).toBeVisible();
  await expect(
    page.getByText(/Currently available only for North Rhine-Westphalia/),
  ).toBeVisible();
  await expect(page.getByRole("option", { name: "English" })).toBeHidden();
  await expect(page.locator(".MuiPopover-root")).toHaveCount(0);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({
    path: "../outputs/polish/help-en-desktop.png",
    fullPage: true,
  });
});
