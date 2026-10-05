export type ReadinessState =
  "incomplete" | "warning" | "complete" | "stale" | "running";

export interface ProjectSummary {
  id: string;
  name: string;
  description: string | null;
  archived: boolean;
  scenario_count: number;
  recent_run_statuses: string[];
  created_at: string;
  updated_at: string;
}

export interface ScenarioRevision {
  id: string;
  scenario_id: string;
  parent_revision_id: string | null;
  revision_number: number;
  document: Record<string, unknown>;
  created_at: string;
  updated_at?: string;
}

export interface ScenarioSummary {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  archived: boolean;
  current_revision_id: string | null;
  revision_number: number;
  readiness_state: ReadinessState;
  preview_id: string | null;
  preview_stale_reason: string | null;
  run_required: boolean;
  area_summary: Record<string, unknown>;
  effective_lhd_threshold: number | null;
  expert_override_count: number;
  created_at: string;
  updated_at: string;
  revision?: ScenarioRevision | null;
}

export interface ProjectDetail extends ProjectSummary {
  scenarios: ScenarioSummary[];
}

export interface Page<T> {
  items: T[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    has_next: boolean;
    has_previous: boolean;
  };
}

export interface ScenarioConfigResponse {
  scenario_id: string;
  revision_id: string;
  revision_number: number;
  parent_revision_id: string | null;
  document: Record<string, unknown>;
  effective_document: Record<string, unknown>;
  merged_toml?: string | null;
  changed_from_default: string[];
  changed_from_parent: string[];
  created_at: string;
}

export type InvalidationEffect =
  "no_downstream_impact" | "preview_invalidated" | "new_run_required";

export interface InvalidationEffects {
  effect: InvalidationEffect;
  changed_paths: string[];
  preview_paths: string[];
  run_only_paths: string[];
  no_impact_paths: string[];
  preview_invalidated: boolean;
  new_run_required: boolean;
  run_only_change: boolean;
  reasons: string[];
}

export interface ScenarioConfigMutationResponse {
  scenario: ScenarioSummary;
  revision: ScenarioRevision;
  invalidation: InvalidationEffects;
  merged_toml?: string | null;
  changed_from_default: string[];
  changed_from_parent: string[];
}

export interface ConfigurationValidationResponse {
  valid: boolean;
  document?: Record<string, unknown> | null;
  effective_document?: Record<string, unknown> | null;
  merged_toml?: string | null;
  changed_paths: string[];
  changed_from_default: string[];
  changed_from_parent: string[];
  invalidation?: InvalidationEffects | null;
  field_errors: Array<{ path: string; message: string; code?: string | null }>;
  warnings: string[];
}

export interface ConfigurationField {
  key: string;
  section: string;
  section_label: string;
  group?: string | null;
  group_label?: string | null;
  label: string;
  description: string;
  data_type:
    | "boolean"
    | "integer"
    | "number"
    | "string"
    | "array"
    | "object"
    | "unknown";
  unit: string | null;
  default: unknown;
  has_default: boolean;
  value: unknown;
  parent_value?: unknown;
  changed_from_default: boolean;
  changed_from_parent: boolean;
  expert_only: boolean;
  editable: boolean;
  runtime_only: boolean;
  impact: "none" | "preview" | "run";
  preprocessing_impact: boolean;
  sensitive: boolean;
  path_policy: string | null;
  constraints: Record<string, unknown>;
}

export interface ConfigurationSchemaResponse {
  version: string;
  fields: ConfigurationField[];
  scenario_id?: string | null;
  revision_id?: string | null;
  parent_revision_id?: string | null;
}

export interface RunHistory {
  id: string;
  scenario_id: string;
  scenario_revision_id: string;
  preview_id: string | null;
  name: string;
  description: string | null;
  status: string;
  failure_summary: string | null;
  warnings: Array<string | Record<string, unknown>>;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateProjectInput {
  name: string;
  description?: string;
}

export interface CreateScenarioInput {
  name: string;
  description?: string;
  source_scenario_id?: string;
  document?: Record<string, unknown>;
}

export interface UpdateScenarioInput {
  expected_revision_id: string;
  name?: string;
  description?: string | null;
  archived?: boolean;
}

export interface UpdateConfigInput {
  expected_revision_id: string;
  document?: Record<string, unknown>;
  toml?: string;
  replace?: boolean;
}
