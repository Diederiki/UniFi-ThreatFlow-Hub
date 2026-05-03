import { api } from "./api";

export type PruneReport = {
  started_at: string;
  finished_at: string;
  audit_logs_deleted: number;
  collector_runs_deleted: number;
  rollups_optimized: string[];
  disk_percent: number;
  disk_free_bytes: number;
  watchdog_fired: boolean;
  actions_taken: string[];
  errors: string[];
};

export type ReclaimEstimate = {
  audit_logs_rows_to_delete: number;
  collector_runs_rows_to_delete: number;
  failed_inserts_rows: number;
  docker_hint: string;
};

export const operationsApi = {
  lastPrune:        () => api<PruneReport | null>("/operations/last-prune"),
  runPrune:         () => api<PruneReport>("/operations/prune", { method: "POST" }),
  reclaimEstimate:  () => api<ReclaimEstimate>("/operations/reclaim-estimate"),
};
