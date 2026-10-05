import type { FeatureCollection } from "./results";

export type CompatibilityStatus = "compatible" | "different" | "unknown";

export interface CompatibilityCheck {
  key: "study_area" | "data_revision" | "model_version" | "result_schema";
  status: CompatibilityStatus;
  values: Record<string, unknown>;
  message: string;
}

export interface ComparisonRun {
  id: string;
  label: string;
  status: string;
  scenario_revision_id: string | null;
  preview_id: string | null;
  model_version: string | null;
  result_schema: string | null;
}

export interface ComparisonMetricRow {
  key?: string;
  technology?: string;
  values: Record<string, number | string | null | undefined>;
  baseline_value: number | string | null | undefined;
  delta?: number | null;
  deltas: Record<string, number | null>;
}

export interface ComparisonNetworkRun {
  run_id: string;
  available: boolean;
  feature_count: number;
  final_network: FeatureCollection | null;
}

export interface ComparisonResource {
  id: string;
  run_ids: string[];
  created_at: string;
  updated_at: string;
  compatibility: CompatibilityCheck[];
  compatible: boolean;
  baseline_run_id: string | null;
  warnings: string[];
  runs: ComparisonRun[];
  kpi_differences: ComparisonMetricRow[];
  kpis?: ComparisonMetricRow[];
  configuration_changes: Array<{
    path: string;
    values: Record<string, unknown>;
    changed: boolean;
    setting_type: "standard" | "expert";
  }>;
  configuration?: ComparisonResource["configuration_changes"];
  network: { runs: ComparisonNetworkRun[] };
  supply: ComparisonMetricRow[];
  portfolio?: ComparisonMetricRow[];
  costs: ComparisonMetricRow[];
  cost_differences?: ComparisonMetricRow[];
}
