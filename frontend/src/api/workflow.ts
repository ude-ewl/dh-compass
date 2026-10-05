import type { FeatureCollection, Pagination } from "./results";

export interface StudyArea {
  scenario_id: string;
  revision_id: string;
  execution_bbox: [number, number, number, number];
  display_geometry: Record<string, unknown> | null;
  source: "bbox" | "geocoded" | "boundary_upload" | "manual" | string;
  imported_filename: string | null;
  crs: string | null;
  validation_issues: ValidationIssue[];
  updated_at: string;
}

export interface ValidationIssue {
  severity: "error" | "warning" | "info";
  code: string;
  message: string;
  path?: string | null;
  remediation?: string | null;
  details?: Record<string, unknown>;
}

export interface BoundaryInspection {
  valid: boolean;
  execution_bbox: [number, number, number, number] | null;
  display_geometry: Record<string, unknown> | null;
  source_crs: string | null;
  normalized_crs: string;
  issues: ValidationIssue[];
  feature_count: number;
}

export interface DatasetAction {
  action: string;
  label: string;
  allowed: boolean;
  reason: string | null;
}

export type DatasetStatus =
  "ready" | "missing" | "invalid" | "stale" | "downloading" | "unavailable";

export interface DatasetDescriptor {
  id: string;
  label: string;
  description: string;
  required: boolean;
  status: DatasetStatus;
  path_display: string | null;
  format: string | null;
  layer: string | null;
  columns: string[];
  crs: string | null;
  extent: number[] | null;
  metadata: Record<string, unknown>;
  issues: ValidationIssue[];
  actions: DatasetAction[];
  checked_at: string;
}

export interface DatasetReadiness {
  scenario_id: string;
  ready: boolean;
  checked_at: string;
  datasets: DatasetDescriptor[];
  blocking_issues: ValidationIssue[];
}

export type PreviewStatus =
  | "queued"
  | "running"
  | "cancellation_requested"
  | "ready"
  | "stale"
  | "failed"
  | "cancelled";

export interface PreviewProgress {
  stage: string | null;
  completed: number | null;
  total: number | null;
  fraction: number | null;
}

export interface PreviewCandidate {
  id: number;
  decision: string | null;
  annual_heat_demand_mwh: number | null;
  average_linear_heat_density_mwh_per_m_a: number | null;
  total_network_length_m: number | null;
  buildings: number | null;
  peak_load_mw: number | null;
  properties: Record<string, unknown>;
}

export interface PreviewSummary {
  candidate_count: number;
  included_buildings: number | null;
  included_demand_mwh: number | null;
  network_length_m: number | null;
  excluded_demand_share_pct: number | null;
  screened_out_edge_count: number | null;
  input_revision: string | null;
  threshold_mwh_per_m_a: number | null;
  linear_heat_density_threshold_mwh_per_m_a?: number | null;
  candidate_summaries: PreviewCandidate[];
  availability: Record<string, boolean>;
}

export interface PreviewArtifact {
  id: string;
  preview_id: string;
  display_name: string;
  description: string | null;
  media_type: string;
  byte_size: number | null;
  status: "pending" | "available" | "failed";
  checksum_sha256: string | null;
  download_url: string | null;
  layer_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface PreviewResource {
  id: string;
  scenario_id: string;
  scenario_revision_id: string;
  status: PreviewStatus;
  stale_reason: string | null;
  linear_heat_density_threshold: number | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  progress: PreviewProgress | null;
  summary: PreviewSummary | null;
  artifacts: PreviewArtifact[];
  failure_summary: string | null;
  warnings: ValidationIssue[];
  events_url: string | null;
  candidates_url: string | null;
}

export interface PreviewCandidateResponse {
  preview_id: string;
  candidate: PreviewCandidate | null;
  available: boolean;
  warnings: ValidationIssue[];
}

export interface DatasetLayerResponse {
  dataset_id: string;
  source: string | null;
  truncated: boolean;
  geojson: FeatureCollection;
}

export type RunStatus =
  | "queued"
  | "running"
  | "cancellation_requested"
  | "cancelled"
  | "completed"
  | "failed";

export interface RunProgress {
  stage: string | null;
  completed: number | null;
  total: number | null;
  fraction: number | null;
}

export interface CandidateProgress {
  completed_candidates: number;
  total_candidates: number | null;
  connected_candidates: number;
  rejected_candidates: number;
  current_candidate_id: number | null;
  current_candidate_index: number | null;
  decision: string | null;
}

export interface RunWarning {
  severity: "error" | "warning" | "info";
  code: string;
  message: string;
  path?: string | null;
  remediation?: string | null;
  details?: Record<string, unknown>;
}

export interface RunArtifact {
  id: string;
  display_name: string;
  description: string | null;
  media_type: string;
  byte_size: number | null;
  status: "pending" | "available" | "failed";
  checksum_sha256: string | null;
  download_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface RunResource {
  id: string;
  scenario_id: string;
  scenario_revision_id: string;
  preview_id: string | null;
  name: string;
  description: string | null;
  output_label: string | null;
  status: RunStatus;
  stage: string | null;
  progress: RunProgress | null;
  candidate_progress: CandidateProgress | null;
  configuration_snapshot: Record<string, unknown>;
  configuration_version: string | null;
  bbox: [number, number, number, number] | null;
  data_snapshot: Record<string, unknown>;
  application_version: string | null;
  solver_name: string | null;
  solver_version: string | null;
  process_identity: {
    pid: number | null;
    started_at: string | null;
    heartbeat_at: string | null;
  } | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
  warnings: RunWarning[];
  failure_summary: string | null;
  failure_details: Record<string, unknown>;
  artifacts: RunArtifact[];
  log_url: string | null;
  events_url: string | null;
  cancel_url: string | null;
  results_url: string | null;
  manifest_url: string | null;
}

export interface RunEvent {
  id: string;
  run_id: string;
  job_kind: "run";
  sequence: number;
  event_type: string;
  data: Record<string, unknown>;
  occurred_at: string;
}

export interface RunLogResponse {
  run_id: string;
  available: boolean;
  content: string;
  truncated: boolean;
}

/**
 * Lightweight run reference used by the recovery list. Configuration,
 * data versions, and artifacts deliberately stay in `RunResource`.
 */
export interface RunSummary {
  id: string;
  name: string;
  status: RunStatus;
  stage: string | null;
  bbox: [number, number, number, number] | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RecentRunsPage {
  items: RunSummary[];
  pagination: Pagination;
}
