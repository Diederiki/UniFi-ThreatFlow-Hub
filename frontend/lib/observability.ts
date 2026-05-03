import { api } from "./api";

export type HostMetrics = {
  ts: number;
  cpu: { percent: number; cores: number; load_avg_1m: number | null };
  memory: { total: number; used: number; available: number; percent: number };
  disk: { total: number; used: number; free: number; percent: number };
  network: { rx_bytes_per_s: number; tx_bytes_per_s: number; rx_total: number; tx_total: number };
};

export type ProcessRow = { pid: number; name: string; rss: number; cpu_percent: number };

export const observabilityApi = {
  host:      () => api<HostMetrics>("/observability/host"),
  processes: (limit = 10) => api<{ items: ProcessRow[] }>(`/observability/host/processes?limit=${limit}`),
};
