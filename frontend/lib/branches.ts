import { api } from "./api";

export type CredentialsMeta = {
  has_username: boolean;
  has_password: boolean;
  has_api_key: boolean;
  has_token: boolean;
};

export type CollectorStatus = {
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

export type Branch = {
  id: string;
  name: string;
  branch_code: string;
  country: string | null;
  city: string | null;
  tags: string[];
  controller_url: string;
  site_id: string;
  gateway_model: string | null;
  auth_method: "local" | "api_key";
  ssl_verify: boolean;
  polling_interval_seconds: number;
  enabled: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
  credentials_meta: CredentialsMeta;
  status: CollectorStatus | null;
};

export type BranchListResponse = { items: Branch[]; total: number };

export type BranchCredentialsIn = {
  username?: string | null;
  password?: string | null;
  api_key?: string | null;
  token?: string | null;
};

export type BranchCreateInput = {
  name: string;
  branch_code: string;
  country?: string | null;
  city?: string | null;
  tags?: string[];
  controller_url: string;
  site_id?: string;
  gateway_model?: string | null;
  auth_method?: "local" | "api_key";
  ssl_verify?: boolean;
  polling_interval_seconds?: number;
  enabled?: boolean;
  notes?: string | null;
  credentials?: BranchCredentialsIn;
};

export type BranchUpdateInput = Partial<BranchCreateInput>;

export type TestConnectionResult = {
  ok: boolean;
  endpoint_used: string | null;
  unifi_os_version: string | null;
  network_app_version: string | null;
  sites_discovered: string[];
  duration_ms: number;
  error: string | null;
  is_mock: boolean;
};

export const branchesApi = {
  list:    () => api<BranchListResponse>("/branches"),
  get:     (id: string) => api<Branch>(`/branches/${id}`),
  create:  (body: BranchCreateInput) => api<Branch>("/branches", { method: "POST", body: JSON.stringify(body) }),
  update:  (id: string, body: BranchUpdateInput) => api<Branch>(`/branches/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  delete:  (id: string) => api<void>(`/branches/${id}`, { method: "DELETE" }),
  enable:  (id: string) => api<Branch>(`/branches/${id}/enable`, { method: "POST" }),
  disable: (id: string) => api<Branch>(`/branches/${id}/disable`, { method: "POST" }),
  test:    (id: string) => api<TestConnectionResult>(`/branches/${id}/test-connection`, { method: "POST" }),
  discover:(id: string) => api<TestConnectionResult>(`/branches/${id}/discover-sites`, { method: "POST" }),
  importFromCloud: (api_key: string) =>
    api<ImportSummary>("/branches/import-from-cloud", { method: "POST", body: JSON.stringify({ api_key }) }),
};

export type ImportSummary = {
  total_seen: number;
  created: number;
  skipped_existing: number;
  failed: number;
  errors: string[];
};
