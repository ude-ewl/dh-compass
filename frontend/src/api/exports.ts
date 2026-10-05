export type ExportKind = "report" | "bundle" | "csv";
export type ExportStatus = "queued" | "running" | "available" | "failed";

export interface ExportJob {
  id: string;
  run_id: string;
  kind: ExportKind;
  status: ExportStatus;
  display_name: string;
  media_type: string;
  byte_size: number | null;
  checksum_sha256: string | null;
  download_url: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface RetentionCleanupResult {
  older_than_days: number;
  dry_run: boolean;
  candidates: number;
  removed: number;
  run_artifacts_preserved: boolean;
}
