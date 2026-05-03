import { api } from "./api";
import type { Trend } from "./dashboard";
import type { Timeframe } from "./timeframe";

export type ScoringWeights = {
  high_risk_event: number;
  medium_risk_event: number;
  low_risk_event: number;
  blocked_event: number;
  repeated_client: number;
  outbound_suspicious: number;
  malware_botnet: number;
  large_transfer: number;
  known_false_positive: number;
};

export type SuspiciousBranch = {
  branch_id: string;
  branch_code: string;
  branch_name: string;
  flows: number;
  blocked: number;
  ids_ips: number;
  high_risk: number;
  medium_risk: number;
  low_risk: number;
  score: number;
};

export type SuspiciousClient = {
  client_ip: string;
  branch_code: string;
  flows: number;
  blocked: number;
  threats: number;
  score: number;
};

export type SuspiciousDestination = {
  destination_ip: string;
  destination_hostname: string | null;
  destination_country: string | null;
  flows: number;
  threats: number;
  score: number;
};

const q = (tf: Timeframe, extra: Record<string, string | number | undefined> = {}) => {
  const p = new URLSearchParams({ timeframe: tf });
  for (const [k, v] of Object.entries(extra)) if (v !== undefined && v !== "") p.set(k, String(v));
  return p.toString();
};

export const suspicionApi = {
  getScoring: () => api<ScoringWeights>("/scoring"),
  putScoring: (w: ScoringWeights) => api<ScoringWeights>("/scoring", { method: "PUT", body: JSON.stringify(w) }),
  branches:     (tf: Timeframe, limit = 20) => api<{ timeframe: string; items: SuspiciousBranch[] }>(`/suspicion/branches?${q(tf, { limit })}`),
  clients:      (tf: Timeframe, limit = 20) => api<{ timeframe: string; items: SuspiciousClient[] }>(`/suspicion/clients?${q(tf, { limit })}`),
  destinations: (tf: Timeframe, limit = 20) => api<{ timeframe: string; items: SuspiciousDestination[] }>(`/suspicion/destinations?${q(tf, { limit })}`),
  trend:        (tf: Timeframe) => api<Trend>(`/suspicion/trend?${q(tf)}`),
};
