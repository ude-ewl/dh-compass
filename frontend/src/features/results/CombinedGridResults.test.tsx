import { render, screen } from "@testing-library/react";
import { CombinedGridResults } from "./CombinedGridResults";

vi.mock("../../components/charts/EChart", () => ({ EChart: () => <div /> }));
vi.mock("../../api/queries", () => ({
  useResultCostsQuery: () => ({
    data: {
      available: true,
      data: {
        grid_breakdown: {
          distribution_pipes_eur: 400,
          connection_pipelines_eur: 100,
          building_connections_eur: 200,
          transfer_stations_eur: 200,
          pumps_eur: 100,
        },
        supply_breakdown: {
          investment: { total_eur: 1000 },
          fixed_om: { total_eur: 500 },
          operational: { net_operational_annual_eur: 500 },
        },
      },
    },
  }),
  useResultSupplyQuery: () => ({
    data: {
      available: true,
      data: {
        supply: { river_heat_pump: { capacity_kw: 20, annual_energy_mwh: 50 } },
        resources: {
          river_heat_pump: { used: 20, limit: 80, unit: "kW" },
          geothermal: { used: 0, limit: 50, unit: "kW" },
        },
      },
    },
  }),
}));

it("shows six final-grid metrics, requested charts, and used versus available potential", () => {
  render(
    <CombinedGridResults
      runId="run-1"
      summary={{
        connected_heat_demand_mwh: 50,
        connected_buildings: 12,
        peak_load_kw: 20,
        final_connection_length_m: 500,
        average_linear_heat_density_mwh_per_m_a: 0.1,
        total_annualized_eur: 3000,
        disconnected_heat_demand_mwh: 999,
      }}
    />,
  );
  for (const label of [
    "Annual demand",
    "Buildings",
    "Peak load",
    "Connection length",
    "Average LHD",
    "Total annualized cost",
  ])
    expect(screen.getByText(label)).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Key results" }),
  ).toBeInTheDocument();
  expect(screen.queryByText(/All values describe/)).not.toBeInTheDocument();
  expect(
    screen.queryByText(/Components are reconstructed/),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "View data" }),
  ).not.toBeInTheDocument();
  for (const title of [
    "Annualized cost breakdown",
    "Installed capacities",
    "Generation mix",
    "Location-dependent potential used",
  ])
    expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
  expect(screen.getByText("River heat pump · 25.0% used")).toBeInTheDocument();
  expect(screen.getByText("Geothermal · 0.0% used")).toBeInTheDocument();
  expect(screen.getByText("20.0 / 80.0 kW")).toBeInTheDocument();
  expect(screen.queryByText(/999/)).not.toBeInTheDocument();
});
