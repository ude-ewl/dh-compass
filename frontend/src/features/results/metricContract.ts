export const METRIC_CONTRACT_VERSION = "1";

export type MetricDefinition = {
  unit: string;
  scope: string;
  timeBasis: string;
  calculationStage: string;
  basis: string;
  provenance: readonly string[];
};

/**
 * Display metadata for values currently rendered by the legacy result views.
 *
 * The registry is intentionally separate from formatters: a formatter knows
 * how to render a unit, while this contract explains what the value means.
 * The redesign can use the same definitions without inheriting the legacy
 * seven-tab navigation.
 */
export const RESULT_METRIC_CONTRACT = {
  "summary.total_heat_demand_mwh": {
    unit: "MWh/a",
    scope: "all screened candidate areas in the study bbox",
    timeBasis: "annual model demand",
    calculationStage: "final reporting",
    basis: "connected plus disconnected candidate demand",
    provenance: ["full_results.json:summary.total_heat_demand_mwh"],
  },
  "summary.connected_heat_demand_mwh": {
    unit: "MWh/a",
    scope: "buildings in the final connected central network",
    timeBasis: "annual model demand",
    calculationStage: "final reporting",
    basis: "sum of selected candidate demand",
    provenance: ["full_results.json:summary.connected_heat_demand_mwh"],
  },
  "summary.disconnected_heat_demand_mwh": {
    unit: "MWh/a",
    scope: "screened candidates not selected for the central network",
    timeBasis: "annual model demand",
    calculationStage: "final reporting",
    basis: "sum of rejected candidate demand",
    provenance: ["full_results.json:summary.disconnected_heat_demand_mwh"],
  },
  "summary.connected_share_pct": {
    unit: "%",
    scope: "all screened candidate demand",
    timeBasis: "annual model demand",
    calculationStage: "final reporting",
    basis: "connected heat demand / total heat demand",
    provenance: ["full_results.json:summary.connected_share_pct"],
  },
  "summary.connected_buildings": {
    unit: "buildings",
    scope: "buildings served by the final central network",
    timeBasis: "snapshot at final solution",
    calculationStage: "final reporting",
    basis: "count of buildings in connected candidates",
    provenance: ["full_results.json:combined_graph.total_buildings"],
  },
  "summary.total_annualized_eur": {
    unit: "€/a",
    scope: "final connected central system",
    timeBasis: "annualized over configured investment duration",
    calculationStage: "final reporting",
    basis: "annualized grid plus supply cost",
    provenance: ["full_results.json:combined_graph.cost.total_annualized_eur"],
  },
  "summary.total_network_length_m": {
    unit: "m",
    scope: "final central network",
    timeBasis: "snapshot at final solution",
    calculationStage: "final reporting",
    basis: "sum of selected network edge lengths",
    provenance: ["full_results.json:combined_graph.total_network_length_m"],
  },
  "summary.peak_load_kw": {
    unit: "kW",
    scope: "final connected central network",
    timeBasis: "maximum modeled demand timestep",
    calculationStage: "final reporting",
    basis: "maximum demand_heat in final solution",
    provenance: ["full_results.json:combined_graph.peak_load_kw"],
  },
  "summary.supply_annualized_eur": {
    unit: "€/a",
    scope: "final connected central supply portfolio",
    timeBasis: "annualized over configured investment duration",
    calculationStage: "final reporting",
    basis: "annualized total cost less annualized grid cost",
    provenance: ["full_results.json:combined_graph.cost.supply_annualized_eur"],
  },
  "summary.grid_annualized_eur": {
    unit: "€/a",
    scope: "final connected central network infrastructure",
    timeBasis: "annualized over configured investment duration",
    calculationStage: "final reporting",
    basis: "annualized network and connection costs",
    provenance: ["full_results.json:combined_graph.cost.grid_annualized_eur"],
  },
  "summary.supply_share_pct": {
    unit: "%",
    scope: "final connected central system annualized cost",
    timeBasis: "annualized cost basis",
    calculationStage: "final reporting",
    basis: "supply annualized cost / total annualized cost",
    provenance: ["full_results.json:combined_graph.cost.supply_share_pct"],
  },
  "summary.grid_share_pct": {
    unit: "%",
    scope: "final connected central system annualized cost",
    timeBasis: "annualized cost basis",
    calculationStage: "final reporting",
    basis: "grid annualized cost / total annualized cost",
    provenance: ["full_results.json:combined_graph.cost.grid_share_pct"],
  },
  "summary.technology_annual_energy_mwh": {
    unit: "MWh/a",
    scope: "one final connected central supply technology",
    timeBasis: "annual modeled production",
    calculationStage: "final reporting",
    basis: "technology-local production, not total demand",
    provenance: ["full_results.json:combined_graph.supply.*"],
  },
  "summary.technology_capacity_kw": {
    unit: "kW",
    scope: "one final connected central supply technology",
    timeBasis: "installed capacity",
    calculationStage: "final reporting",
    basis: "thermal or electrical technology capacity",
    provenance: ["full_results.json:combined_graph.supply.*"],
  },
  "summary.technology_energy_share_pct": {
    unit: "%",
    scope: "final connected central supply portfolio",
    timeBasis: "annual modeled production",
    calculationStage: "final reporting",
    basis: "technology production share",
    provenance: ["viewer_data.json:subgraphs.*.supply.*.energy_share_pct"],
  },
  "summary.grid_raw_total_eur": {
    unit: "€",
    scope: "final connected central network infrastructure",
    timeBasis: "capital value at model price basis",
    calculationStage: "final reporting",
    basis:
      "raw grid investment before annualization and residual-value treatment",
    provenance: [
      "full_results.json:combined_graph.cost.grid_breakdown.raw_total_eur",
    ],
  },
  "summary.total_heat_production_mwh": {
    unit: "MWh/a",
    scope: "final connected central supply portfolio",
    timeBasis: "annual modeled production",
    calculationStage: "final reporting",
    basis: "sum of reported supply technology production",
    provenance: ["full_results.json:combined_graph.total_heat_production_mwh"],
  },
  "summary.cost_per_connected_mwh": {
    unit: "€/MWh",
    scope: "final connected central system",
    timeBasis: "annualized cost divided by annual demand",
    calculationStage: "frontend-derived from final reporting values",
    basis: "total annualized cost / connected annual demand",
    provenance: [
      "summary.total_annualized_eur",
      "summary.connected_heat_demand_mwh",
    ],
  },
  "candidate.annual_heat_demand_mwh": {
    unit: "MWh/a",
    scope: "one candidate area",
    timeBasis: "annual model demand",
    calculationStage: "candidate evaluation",
    basis: "candidate-local demand",
    provenance: ["viewer_data.json:subgraphs.*.annual_heat_demand_mwh"],
  },
  "candidate.buildings": {
    unit: "buildings",
    scope: "one candidate area",
    timeBasis: "snapshot at candidate evaluation",
    calculationStage: "candidate evaluation",
    basis: "candidate-local building count",
    provenance: ["viewer_data.json:subgraphs.*.buildings"],
  },
  "candidate.peak_load_kw": {
    unit: "kW",
    scope: "one candidate area",
    timeBasis: "maximum modeled demand timestep",
    calculationStage: "candidate evaluation",
    basis: "peak_load_mw is converted to kW when that is the available field",
    provenance: [
      "viewer_data.json:subgraphs.*.peak_load_kw",
      "full_results.json:subgraphs.*.peak_load_mw",
    ],
  },
  "candidate.total_network_length_m": {
    unit: "m",
    scope: "trial network inside one candidate area",
    timeBasis: "snapshot at candidate evaluation",
    calculationStage: "candidate evaluation",
    basis: "candidate-local network length, not final total",
    provenance: ["viewer_data.json:subgraphs.*.total_network_length_m"],
  },
  "candidate.connection_length_m": {
    unit: "m",
    scope: "connection path for one candidate",
    timeBasis: "snapshot at candidate evaluation",
    calculationStage: "candidate evaluation",
    basis: "candidate-local connecting path",
    provenance: ["viewer_data.json:subgraphs.*.connection_length_m"],
  },
  "candidate.average_lhd": {
    unit: "MWh/(m·a)",
    scope: "one candidate area",
    timeBasis: "annual model demand",
    calculationStage: "candidate preprocessing/evaluation",
    basis: "candidate demand divided by candidate network length",
    provenance: [
      "full_results.json:subgraphs.*.average_linear_heat_density_mwh_per_m_a",
    ],
  },
  "candidate.central_cost": {
    unit: "€/a",
    scope: "trial central connection of one candidate",
    timeBasis: "annualized over configured investment duration",
    calculationStage: "candidate evaluation",
    basis: "candidate-local annualized central alternative",
    provenance: ["viewer_data.json:subgraphs.*.central_cost"],
  },
  "candidate.decentral_cost": {
    unit: "€/a",
    scope: "decentralized alternative for one candidate",
    timeBasis: "annualized over configured investment duration",
    calculationStage: "candidate evaluation",
    basis: "candidate-local annualized decentralized alternative",
    provenance: ["viewer_data.json:subgraphs.*.decentral_cost"],
  },
  "candidate.central_grid_cost_raw": {
    unit: "€",
    scope: "trial central connection of one candidate",
    timeBasis: "capital value at model price basis",
    calculationStage: "candidate evaluation",
    basis: "raw capital value, not annualized",
    provenance: ["viewer_data.json:subgraphs.*.central_grid_cost_raw"],
  },
  "candidate.decision_margin": {
    unit: "€/a",
    scope: "one candidate alternative comparison",
    timeBasis: "annualized over configured investment duration",
    calculationStage: "frontend-derived from candidate evaluation",
    basis: "decentralized cost minus central cost",
    provenance: ["candidate.decentral_cost", "candidate.central_cost"],
  },
  "candidate.decision_step": {
    unit: "step",
    scope: "optimization candidate ordering",
    timeBasis: "run sequence",
    calculationStage: "optimization orchestration",
    basis: "one-based display position",
    provenance: ["viewer_data.json:iterations.*.step"],
  },
  "candidate.technology_annual_energy_mwh": {
    unit: "MWh/a",
    scope: "one candidate supply portfolio",
    timeBasis: "annual modeled production",
    calculationStage: "candidate evaluation",
    basis: "technology-local production, not total demand",
    provenance: ["viewer_data.json:subgraphs.*.supply.*"],
  },
  "candidate.storage_capacity_kwh": {
    unit: "kWh",
    scope: "one candidate storage asset",
    timeBasis: "installed capacity",
    calculationStage: "candidate evaluation",
    basis: "capacity, not annual energy",
    provenance: ["viewer_data.json:subgraphs.*.storage.*.capacity_kwh"],
  },
  "candidate.storage_power_kw": {
    unit: "kW",
    scope: "one candidate storage asset",
    timeBasis: "installed peak charge/discharge power",
    calculationStage: "candidate evaluation",
    basis: "power, not storage capacity",
    provenance: ["viewer_data.json:subgraphs.*.storage.*.power_kw"],
  },
  "candidate.total_heat_production_mwh": {
    unit: "MWh/a",
    scope: "one candidate supply portfolio",
    timeBasis: "annual modeled production",
    calculationStage: "candidate evaluation",
    basis: "candidate-local production total",
    provenance: ["viewer_data.json:subgraphs.*.total_heat_production_mwh"],
  },
  "candidate.cost_breakdown_investment": {
    unit: "€/a",
    scope: "one candidate supply portfolio",
    timeBasis: "annualized over configured investment duration",
    calculationStage: "candidate evaluation",
    basis: "reconstructed annualized investment component",
    provenance: [
      "viewer_data.json:subgraphs.*.cost_breakdown.investment.total_eur",
    ],
  },
  "candidate.cost_breakdown_fixed_om": {
    unit: "€/a",
    scope: "one candidate supply portfolio",
    timeBasis: "annualized over configured investment duration",
    calculationStage: "candidate evaluation",
    basis: "reconstructed annualized fixed O&M component",
    provenance: [
      "viewer_data.json:subgraphs.*.cost_breakdown.fixed_om.total_eur",
    ],
  },
  "candidate.cost_breakdown_operational": {
    unit: "€/a",
    scope: "one candidate supply portfolio",
    timeBasis: "annual operating basis",
    calculationStage: "candidate evaluation",
    basis: "net operational cost after modeled revenues",
    provenance: [
      "viewer_data.json:subgraphs.*.cost_breakdown.operational.net_operational_annual_eur",
    ],
  },
  "cluster.n_buildings": {
    unit: "buildings",
    scope: "one decentralized demand cluster inside one candidate",
    timeBasis: "snapshot at candidate evaluation",
    calculationStage: "decentralized clustering",
    basis: "cluster-local building count",
    provenance: ["viewer_data.json:subgraphs.*.clusters.*.n_buildings"],
  },
  "cluster.total_demand_mwh": {
    unit: "MWh/a",
    scope: "one decentralized demand cluster inside one candidate",
    timeBasis: "annual model demand",
    calculationStage: "decentralized clustering",
    basis: "cluster-local demand",
    provenance: ["viewer_data.json:subgraphs.*.clusters.*.total_demand_mwh"],
  },
  "cluster.scaled_annualized_cost_eur": {
    unit: "€/a",
    scope: "one scaled decentralized demand cluster",
    timeBasis: "annualized over configured investment duration",
    calculationStage: "decentralized clustering",
    basis: "cluster-local scaled cost, not final-system total",
    provenance: [
      "viewer_data.json:subgraphs.*.clusters.*.scaled_annualized_cost_eur",
    ],
  },
} as const satisfies Record<string, MetricDefinition>;

export type ResultMetricId = keyof typeof RESULT_METRIC_CONTRACT;

export function metricDefinition(
  id: ResultMetricId,
): (typeof RESULT_METRIC_CONTRACT)[ResultMetricId] {
  return RESULT_METRIC_CONTRACT[id];
}
