import { api } from "./api";

export type CollectorBranchStatus = {
  branch_id: string;
  branch_name: string;
  branch_code: string;
  enabled: boolean;
  status: string;
  last_success_at: string | null;
  last_error_at: string | null;
  last_error: string | null;
  last_duration_ms: number | null;
  last_event_count: number | null;
  last_endpoint_used: string | null;
  unifi_os_version: string | null;
  network_app_version: string | null;
  collector_version: string | null;
  updated_at: string | null;
};

export type CollectorStatusList = { items: CollectorBranchStatus[]; total: number };

export type CollectorRun = {
  id: number;
  branch_id: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  event_count: number | null;
  error_message: string | null;
  endpoint_used: string | null;
  duration_ms: number | null;
};

export const collectorsApi = {
  status: () => api<CollectorStatusList>("/collectors/status"),
  runs:   (branchId?: string, limit = 50) =>
    api<{ items: CollectorRun[] }>(`/collectors/runs?limit=${limit}${branchId ? `&branch_id=${branchId}` : ""}`),
  runBranch: (branchId: string) =>
    api<{ queued: boolean; branch_id: string }>(`/collectors/run-branch/${branchId}`, { method: "POST" }),
};
