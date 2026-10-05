import { tr } from "../../i18n/translate";
import type { CostResult, SupplyResult } from "../../api/results";

export const techLabels: Record<string, string> = {
  heat_pump: "Heat pump",
  electric_boiler: "Electric boiler",
  heat_boiler: "Gas boiler",
  chp: "CHP",
  biomass_boiler: "Biomass boiler",
  biomass_chp: "Biomass CHP",
  solar_thermal: "Solar thermal",
  geothermal: "Geothermal",
  waste_heat: "Waste heat",
  river_heat_pump: "River heat pump",
  wwtp_heat_pump: "Wastewater heat pump",
  pv: "PV",
  boiler: "Boiler",
  electrode_boiler: "Electrode boiler",
  industrial_excess_heat: "Industrial excess heat",
  waste_to_energy: "Waste to energy",
};
export const technologyLabel = (name: string) =>
  tr(techLabels[name] ?? name.replaceAll("_", " "));
export function finite(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : undefined;
}
function object(value: unknown): Record<string, unknown> {
  return value && typeof value === "object"
    ? (value as Record<string, unknown>)
    : {};
}

/** Grid components in full_results are already annualized; never apply a second annuity. */
export function costSegments(costs: CostResult) {
  const grid = object(costs.grid_breakdown);
  const supply = object(costs.supply_breakdown);
  const distribution = finite(grid.distribution_pipes_eur);
  const connections = finite(grid.connection_pipelines_eur);
  return [
    {
      name: tr("Distribution (including connecting pipelines)"),
      values: [
        distribution !== undefined && connections !== undefined
          ? distribution + connections
          : undefined,
        0,
      ],
      color: "#607D8B",
    },
    {
      name: tr("Building connections"),
      values: [finite(grid.building_connections_eur), 0],
      color: "#8BC34A",
    },
    {
      name: tr("Transfer stations"),
      values: [finite(grid.transfer_stations_eur), 0],
      color: "#FFC107",
    },
    {
      name: tr("Pumps"),
      values: [finite(grid.pumps_eur), 0],
      color: "#00BCD4",
    },
    {
      name: tr("Investment"),
      values: [0, finite(object(supply.investment).total_eur)],
      color: "#1976D2",
    },
    {
      name: tr("O&M"),
      values: [0, finite(object(supply.fixed_om).total_eur)],
      color: "#64B5F6",
    },
    {
      name: tr("Variable cost (fuel & electricity)"),
      values: [
        0,
        finite(object(supply.operational).net_operational_annual_eur),
      ],
      color: "#BBDEFB",
    },
  ];
}

export function technologyData(result: SupplyResult) {
  return Object.entries(result.supply ?? {})
    .filter(([key]) => key !== "pv")
    .map(([key, value]) => {
      const chp = key === "chp" || key === "biomass_chp";
      return {
        name: technologyLabel(key),
        capacity: finite(chp ? value.capacity_th_kw : value.capacity_kw),
        energy: finite(
          chp ? value.annual_heat_energy_mwh : value.annual_energy_mwh,
        ),
      };
    });
}
