export type CalculationStatus =
  "queued" | "running" | "completed" | "failed" | "cancelled";

export interface CalculationContract {
  contract_version: string;
  command: {
    method: "POST";
    path: string;
    body: { bbox: ["west", "south", "east", "north"] };
    idempotency_header: string;
    idempotency: {
      same_key_same_bbox: string;
      same_key_different_bbox: string;
      preflight_rejection: string;
      post_acceptance_failure: string;
    };
  };
  bbox: {
    crs: "EPSG:4326" | string;
    coordinate_order: ["west", "south", "east", "north"];
    coverage_bbox: [number, number, number, number];
    min_area_km2: number;
    max_area_km2: number;
    area_calculation: string;
  };
  defaults: {
    configuration_version: string;
    source: string;
    frontend_may_not_override: boolean;
  };
  lifecycle: {
    statuses: CalculationStatus[];
    terminal_statuses: CalculationStatus[];
    response: {
      run_id: string;
      status: "queued";
      status_url: string;
      bbox: ["west", "south", "east", "north"];
      configuration_version: string;
    };
  };
}

export interface CalculationAccepted {
  run_id: string;
  status: CalculationStatus;
  status_url: string;
  bbox: [number, number, number, number];
  configuration_version: string;
  submitted_at?: string | null;
  idempotency_replayed?: boolean;
  details?: Record<string, unknown>;
}
