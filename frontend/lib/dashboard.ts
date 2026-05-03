import { api } from "./api";
import type { Timeframe } from "./timeframe";

export type OverviewKpis = {
  total_branches: number;
  online_collectors: number;
  total_flows: number;
  allowed_flows: number;
  blocked_flows: number;
  ids_ips_events: number;
  high_risk_events: number;
  medium_risk_events: number;
  low_risk_events: number;
  unique_clients: number;
  top_suspicious_branch: string | null;
  top_suspicious_client: string | null;
};

export type BranchHeatRow = {
  branch_id: string;
  branch_code: string;
  branch_name: string;
  flows: number;
  blocked: number;
  ids_ips: number;
  high_risk: number;
  suspicion_score: number;
};

export type Overview = {
  timeframe: string;
  kpis: OverviewKpis;
  branch_heat: BranchHeatRow[];
};

export type TrendPoint = { t: string; value: number };
export type TrendSeries = { name: string; points: TrendPoint[] };
export type Trend = { timeframe: string; bucket_label: string; series: TrendSeries[] };

export type TopItem = { label: string; value: number };
export type Top = { timeframe: string; items: TopItem[] };

export type FlowEvent = {
  event_id: string;
  event_hash: string;
  branch_code: string;
  branch_name: string;
  event_time: string;
  action: string;
  risk: string;
  severity: string;
  policy_type: string;
  policy_name: string | null;
  source_ip: string;
  source_hostname: string | null;
  destination_ip: string;
  destination_port: number | null;
  destination_hostname: string | null;
  destination_country: string | null;
  protocol: string | null;
  application: string | null;
  application_category: string | null;
  bytes_up: number;
  bytes_down: number;
};

export type ThreatEvent = FlowEvent & {
  signature: string;
  threat_category: string | null;
  client_ip: string | null;
};

export type EventsPage<T = FlowEvent | ThreatEvent> = {
  timeframe: string;
  items: T[];
  next_offset: number | null;
  total_estimate: number;
};

export type ClientSummary = {
  client_ip: string;
  branch_code: string;
  flows: number;
  blocked: number;
  threats: number;
  bytes_up: number;
  bytes_down: number;
};

export type ClientList = { timeframe: string; items: ClientSummary[] };

const q = (tf: Timeframe, extra: Record<string, string | number | undefined> = {}) => {
  const params = new URLSearchParams({ timeframe: tf });
  for (const [k, v] of Object.entries(extra)) if (v !== undefined && v !== "") params.set(k, String(v));
  return params.toString();
};

export const dashboardApi = {
  overview:     (tf: Timeframe) => api<Overview>(`/dashboard/overview?${q(tf)}`),
  trafficTrend: (tf: Timeframe) => api<Trend>(`/dashboard/traffic-trend?${q(tf)}`),
  threatTrend:  (tf: Timeframe) => api<Trend>(`/dashboard/threat-trend?${q(tf)}`),
};

export const eventsApi = {
  threats: (tf: Timeframe, opts: { branch_id?: string; severity?: string; signature?: string; source_ip?: string; destination_ip?: string; action?: string; page?: number; page_size?: number } = {}) =>
    api<EventsPage<ThreatEvent>>(`/threats?${q(tf, opts)}`),
  blocked: (tf: Timeframe, opts: { branch_id?: string; page?: number; page_size?: number } = {}) =>
    api<EventsPage<FlowEvent>>(`/blocked?${q(tf, opts)}`),
};

export const topApi = {
  destinations: (tf: Timeframe, limit = 20) => api<Top>(`/top/destinations?${q(tf, { limit })}`),
  domains:      (tf: Timeframe, limit = 20) => api<Top>(`/top/domains?${q(tf, { limit })}`),
  applications: (tf: Timeframe, limit = 20) => api<Top>(`/top/applications?${q(tf, { limit })}`),
  categories:   (tf: Timeframe, limit = 20) => api<Top>(`/top/categories?${q(tf, { limit })}`),
  clients:      (tf: Timeframe, limit = 20) => api<Top>(`/top/clients?${q(tf, { limit })}`),
  countries:    (tf: Timeframe, limit = 20) => api<Top>(`/top/countries?${q(tf, { limit })}`),
};

export const clientsApi = {
  list: (tf: Timeframe, search = "", limit = 50) => api<ClientList>(`/clients?${q(tf, { search, limit })}`),
};
