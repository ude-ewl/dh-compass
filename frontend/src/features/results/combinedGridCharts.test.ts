import { costSegments, technologyData } from "./combinedGridCharts";

it("groups connecting pipelines with distribution without annualizing twice", () => {
  const segments = costSegments({
    grid_breakdown: {
      raw_total_eur: 10000,
      total_annualized_eur: 1000,
      distribution_pipes_eur: 400,
      connection_pipelines_eur: 100,
      building_connections_eur: 200,
      transfer_stations_eur: 200,
      pumps_eur: 100,
    },
    supply_breakdown: {
      investment: { total_eur: 1000 },
      fixed_om: { total_eur: 500 },
      operational: { net_operational_annual_eur: -100 },
    },
  });
  expect(segments.map((item) => item.values)).toEqual([
    [500, 0],
    [200, 0],
    [200, 0],
    [100, 0],
    [0, 1000],
    [0, 500],
    [0, -100],
  ]);
  expect(costSegments({})[0].values[0]).toBeUndefined();
});

it("uses CHP thermal output and excludes PV from the heat generation mix", () => {
  const data = technologyData({
    supply: {
      chp: {
        capacity_th_kw: 40,
        capacity_el_kw: 20,
        annual_heat_energy_mwh: 90,
        annual_energy_mwh: 30,
      },
      heat_pump: { capacity_kw: 50, annual_energy_mwh: 100 },
      pv: { capacity_kw: 80, annual_energy_mwh: 200 },
    },
  });
  expect(data).toEqual([
    { name: "CHP", capacity: 40, energy: 90 },
    { name: "Heat pump", capacity: 50, energy: 100 },
  ]);
});
