import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { HelpPage } from "../features/help/HelpPage";
import { formatNumber } from "../features/results/format";
import { getLocale, setLocale } from "./locale";
import { t } from "./messages";
import { tr } from "./translate";

vi.mock("../api/queries", () => ({
  useHealthQuery: () => ({ isPending: false, isError: false }),
}));
beforeEach(() => {
  const saved = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => saved.get(key) ?? null,
    setItem: (key: string, value: string) => saved.set(key, value),
    removeItem: (key: string) => saved.delete(key),
    clear: () => saved.clear(),
  });
});
afterEach(() => {
  cleanup();
  act(() => setLocale("en"));
  vi.unstubAllGlobals();
});

it("switches the actual header and help page, remembers the choice and retains input state", async () => {
  setLocale("en");
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={["/help"]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route
            path="help"
            element={
              <>
                <input aria-label="draft" defaultValue="7.10000" />
                <HelpPage />
              </>
            }
          />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
  expect(
    screen.getByRole("heading", { name: "About DH-COMPASS" }),
  ).toBeInTheDocument();
  await user.type(screen.getByLabelText("draft"), "1");
  await user.click(
    screen.getByRole("combobox", { name: "Language / Sprache" }),
  );
  await user.click(screen.getByRole("option", { name: "Deutsch" }));
  expect(
    screen.getByRole("heading", { name: "Über DH-COMPASS" }),
  ).toBeInTheDocument();
  expect(
    screen.getAllByRole("link", { name: "Neue Berechnung" }).length,
  ).toBeGreaterThan(0);
  expect(
    screen.getByText(/Derzeit nur für Nordrhein-Westfalen/),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Konfigurationsanleitung" }),
  ).toHaveAttribute(
    "href",
    "https://github.com/ude-ewl/DH-COMPASS/blob/main/docs/configuration.md",
  );
  expect(screen.getByLabelText("draft")).toHaveValue("7.100001");
  expect(localStorage.getItem("dh-compass:language")).toBe("de");
  expect(document.documentElement.lang).toBe("de");
  expect(formatNumber(1234.5, 1)).toBe("1\u202f234,5");
  await user.click(
    screen.getByRole("combobox", { name: "Language / Sprache" }),
  );
  await user.click(screen.getByRole("option", { name: "English" }));
  expect(
    screen.getByRole("heading", { name: "About DH-COMPASS" }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("draft")).toHaveValue("7.100001");
  expect(formatNumber(1234.5, 1)).toBe("1\u202f234.5");
});

it("interpolates messages and translates dynamic labels without changing data", () => {
  setLocale("de");
  expect(getLocale()).toBe("de");
  expect(t("comparisonSelectionCount", { count: 2 })).toBe(
    "2 von 4 Berechnungen ausgewählt",
  );
  expect(tr("Step 2 / 4")).toBe("Schritt 2 / 4");
  expect(tr("The selected area is larger than 2,500 km².")).toBe(
    "Das gewählte Gebiet ist größer als 2,500 km².",
  );
  expect(tr("inputs/default.toml")).toBe("inputs/default.toml");
  expect(tr(1234.5)).toBe(1234.5);
});
