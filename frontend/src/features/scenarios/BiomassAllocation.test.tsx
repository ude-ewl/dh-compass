import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setLocale } from "../../i18n/locale";
import { updateScenarioConfig } from "../../api/client";
import { BiomassAllocationDetails, BiomassMunicipalitySelection } from "./BiomassAllocation";

const configuration = vi.hoisted(() => ({
  revision_id: "revision-1",
  effective_document: { resources: { biomass_municipality_ags: [] } },
}));
vi.mock("../../api/queries", () => ({
  useScenarioConfigQuery: () => ({ data: configuration, isError: false }),
}));
vi.mock("../../api/client", async (original) => ({
  ...(await original<typeof import("../../api/client")>()),
  updateScenarioConfig: vi.fn().mockResolvedValue({}),
}));

const allocation = {
  method: "municipality_population", fuel_budget_mwh: 14596.7075, budget_fraction: 1,
  population_date: "2024-12-31",
  population_data: { attribution: "© BKG (2026), dl-de/by-2-0" },
  municipalities: [{ ags: "05958012", name: "Brilon", population: 25424,
    region_population: 3571898, population_share: 0.0071177844, allocated_fuel_mwh: 14596.7075 }],
};
const choices = [
  { ags: "05958012", name: "Brilon", population: 25424 },
  { ags: "05958013", name: "Neighbour", population: 9000 },
];

afterEach(() => {
  act(() => setLocale("en"));
  vi.clearAllMocks();
});

it("explains fuel allowance and provenance in both languages without changing identifiers", () => {
  render(<BiomassAllocationDetails value={allocation} />);
  expect(screen.getByText("Biomass fuel budget")).toBeInTheDocument();
  expect(screen.getByText(/Brilon \(05958012\)/)).toBeInTheDocument();
  expect(screen.getByText(/Fuel energy, not useful heat/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "BKG" })).toHaveAttribute("href", "https://www.bkg.bund.de");
  act(() => setLocale("de"));
  expect(screen.getByText("Biomasse-Brennstoffbudget")).toBeInTheDocument();
  expect(screen.getByText(/Brennstoffenergie, keine Nutzwärme/)).toBeInTheDocument();
  expect(screen.getByText(/Brilon \(05958012\)/)).toBeInTheDocument();
  expect(screen.getByText(/2024-12-31/)).toBeInTheDocument();
});

it("retains explicit selection on language switch and saves only the selected AGS with revision protection", async () => {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  render(<QueryClientProvider client={client}>
    <BiomassMunicipalitySelection scenarioId="scenario-1" value={choices} />
  </QueryClientProvider>);
  expect(screen.getByRole("button", { name: "Apply municipality selection" })).toBeDisabled();
  await userEvent.click(screen.getByRole("checkbox", { name: /Brilon/ }));
  act(() => setLocale("de"));
  expect(screen.getByRole("checkbox", { name: /Brilon/ })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: /Neighbour/ })).not.toBeChecked();
  await userEvent.click(screen.getByRole("button", { name: "Gemeindeauswahl übernehmen" }));
  await waitFor(() => expect(updateScenarioConfig).toHaveBeenCalledWith("scenario-1", {
    expected_revision_id: "revision-1", replace: false,
    document: { resources: { biomass_municipality_ags: ["05958012"] } },
  }));
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["scenario", "scenario-1"] });
});

it("does not invent an allowance for old results without allocation metadata", () => {
  render(<BiomassAllocationDetails value={undefined} />);
  expect(screen.queryByText("Biomass fuel budget")).not.toBeInTheDocument();
});
