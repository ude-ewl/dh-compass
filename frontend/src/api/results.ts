/**
 * Artifact metadata is served by either the legacy-output or managed-run
 * router, depending on the run identifier. Managed records use `status` and
 * omit legacy-only `available`, `kind`, and `error` fields.
 */
export type ArtifactStatus =
  "available" | "missing" | "invalid" | "pending" | "failed";

export interface ArtifactAvailability {
  id: string;
  display_name: string;
  kind?: string;
  media_type: string;
  status: ArtifactStatus;
  available?: boolean;
  byte_size: number | null;
  checksum_sha256: string | null;
  error?: string | null;
  download_url: string | null;
}

export interface RunManifest {
  id: string;
  scenario: string;
  timestamp: string;
  display_name: string;
  status: "completed" | "incomplete";
  source: "legacy_output";
  legacy: boolean;
  created_at: string;
  updated_at: string;
  summary: Record<string, unknown> | null;
  artifacts: ArtifactAvailability[];
  warnings: string[];
}

export interface Pagination {
  page: number;
  page_size: number;
  total: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface Page<T> {
  items: T[];
  pagination: Pagination;
}

export interface ResultProvenance {
  run_id: string;
  adapter: string;
  source_artifacts: string[];
  artifact_checksums: Record<string, string | null>;
  immutable: boolean;
}

export interface ResultEnvelope<T> {
  available: boolean;
  data: T | null;
  source_artifacts: string[];
  warnings: string[];
  availability: Record<string, boolean>;
  provenance: ResultProvenance | null;
  content_hash: string | null;
}

export interface GeoJsonGeometry {
  type: string;
  coordinates?: unknown;
  geometries?: GeoJsonGeometry[];
}

export interface GeoJsonFeature {
  type: "Feature";
  geometry: GeoJsonGeometry | null;
  properties: Record<string, unknown> | null;
  id?: string | number;
}

export interface FeatureCollection {
  type: "FeatureCollection";
  features: GeoJsonFeature[];
  [key: string]: unknown;
}

export interface NetworkResult {
  final_network: FeatureCollection | null;
  candidate_network: FeatureCollection;
  lhd: FeatureCollection | null;
  connection_paths: FeatureCollection;
  buildings?: FeatureCollection | null;
  screened_out?: FeatureCollection | null;
  availability: {
    final_network: boolean;
    candidate_network: boolean;
    lhd: boolean;
    connection_paths: boolean;
    buildings?: boolean;
    screened_out?: boolean;
    [key: string]: boolean | undefined;
  };
}

export interface CandidateRecord extends Record<string, unknown> {
  id: number;
  decision: "connected" | "rejected";
  annual_heat_demand_mwh?: number;
  peak_load_kw?: number;
  peak_load_mw?: number;
  buildings?: number;
  total_network_length_m?: number;
  avg_lhd?: number;
  average_linear_heat_density_mwh_per_m_a?: number;
  central_cost?: number;
  decentral_cost?: number;
  connection_length_m?: number;
  central_grid_cost_raw?: number;
  decision_margin_eur?: number;
  difference_eur?: number;
  iteration_step?: number;
  cost_breakdown?: Record<string, unknown>;
  supply?: Record<string, SupplyTechnology>;
  storage?: Record<string, Record<string, unknown>>;
  total_heat_production_mwh?: number;
  edges_geojson?: FeatureCollection;
  clusters?: Record<string, unknown>[];
}

export interface IterationRecord extends Record<string, unknown> {
  step: number;
  subgraph_id: number;
  decision: "connected" | "rejected";
  central_cost_total?: number;
  marginal_central_cost?: number;
  decentral_cost?: number;
  cumulative_connected_ids?: number[];
  cumulative_supply?: SupplyResult;
  connecting_path_geojson?: FeatureCollection | null;
}

export interface SupplyTechnology extends Record<string, unknown> {
  annual_energy_mwh?: number;
  annual_heat_energy_mwh?: number;
  capacity_kw?: number;
  capacity_th_kw?: number;
  capacity_el_kw?: number;
  energy_share_pct?: number;
}

export interface SupplyResult extends Record<string, unknown> {
  supply?: Record<string, SupplyTechnology>;
  storage?: Record<string, Record<string, unknown>>;
  resources?: Record<
    string,
    {
      used?: number;
      limit?: number;
      utilization_pct?: number;
      unit?: string | null;
      [key: string]: unknown;
    }
  >;
  total_heat_production_mwh?: number | null;
}

export interface CostResult extends Record<string, unknown> {
  total_annualized_eur?: number;
  supply_annualized_eur?: number;
  grid_annualized_eur?: number;
  supply_share_pct?: number;
  grid_share_pct?: number;
  supply_breakdown?: Record<string, unknown>;
  grid_breakdown?: Record<string, unknown>;
  by_candidate?: Record<string, number>;
  by_technology?: Record<string, number>;
}

export interface DecentralCandidateRecord extends CandidateRecord {
  difference_eur?: number;
  clusters_available?: boolean;
  supply?: Record<string, SupplyTechnology>;
  storage?: Record<string, Record<string, unknown>>;
  total_heat_production_mwh?: number;
}

export type DecentralResult = DecentralCandidateRecord[];

export interface TimeSeriesResult {
  points: Array<Record<string, unknown>>;
  series: Record<string, Array<number | string | null>>;
  series_names: string[];
  original_points: number;
  returned_points: number;
  downsampled: boolean;
  max_points: number;
}

export interface ArtifactPage {
  items: ArtifactAvailability[];
  pagination: Pagination;
}
