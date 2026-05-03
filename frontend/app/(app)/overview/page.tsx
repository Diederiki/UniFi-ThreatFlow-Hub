"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { dashboardApi, type Overview, type Trend } from "@/lib/dashboard";
import { TrendArea } from "@/components/charts/TrendArea";
import { useTimeframe } from "@/lib/timeframe";

function fmtNum(n: number): string { return n.toLocaleString(); }

function Kpi({ label, value, accent }: { label: string; value: string | number; accent?: "danger" | "warn" | "success" | "accent" }) {
  const cls =
    accent === "danger"  ? "text-danger"  :
    accent === "warn"    ? "text-warn"    :
    accent === "success" ? "text-success" :
    accent === "accent"  ? "text-accent"  : "text-text";
  return (
    <div className="panel p-4">
      <div className="text-xs text-muted uppercase tracking-wide">{label}</div>
      <div className={`mt-2 text-2xl num ${cls}`}>{value}</div>
    </div>
  );
}

export default function OverviewPage() {
  const { timeframe } = useTimeframe();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [traffic, setTraffic] = useState<Trend | null>(null);
  const [threat, setThreat] = useState<Trend | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    try {
      const [o, t, th] = await Promise.all([
        dashboardApi.overview(timeframe),
        dashboardApi.trafficTrend(timeframe),
        dashboardApi.threatTrend(timeframe),
      ]);
      setOverview(o); setTraffic(t); setThreat(th);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    }
  }

  useEffect(() => {
    reload();
    const id = setInterval(reload, 30_000);
    return () => clearInterval(id);
  }, [timeframe]);

  if (error) return <div className="panel p-4 text-sm text-danger border-danger/30">{error}</div>;
  if (!overview) return <div className="text-muted text-sm">Loading…</div>;

  const k = overview.kpis;
  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold">Overview</h1>
          <p className="text-xs text-muted">Last {overview.timeframe} · auto-refresh 30s</p>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 gap-4">
        <Kpi label="Branches"        value={fmtNum(k.total_branches)} />
        <Kpi label="Online collectors" value={fmtNum(k.online_collectors)} accent="accent" />
        <Kpi label="Flows"           value={fmtNum(k.total_flows)} />
        <Kpi label="Allowed"         value={fmtNum(k.allowed_flows)} accent="success" />
        <Kpi label="Blocked"         value={fmtNum(k.blocked_flows)} accent="danger" />
        <Kpi label="IDS / IPS"       value={fmtNum(k.ids_ips_events)} accent="accent" />
        <Kpi label="High risk"       value={fmtNum(k.high_risk_events)} accent="danger" />
        <Kpi label="Medium risk"     value={fmtNum(k.medium_risk_events)} accent="warn" />
        <Kpi label="Unique clients"  value={fmtNum(k.unique_clients)} />
        <Kpi label="Top sus. branch" value={k.top_suspicious_branch ?? "—"} accent="warn" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="panel p-4">
          <div className="flex items-baseline justify-between mb-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Traffic ({traffic?.bucket_label ?? "—"})</h2>
            <span className="text-xs text-muted">allowed vs blocked</span>
          </div>
          <TrendArea trend={traffic} />
        </div>
        <div className="panel p-4">
          <div className="flex items-baseline justify-between mb-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Threats ({threat?.bucket_label ?? "—"})</h2>
            <span className="text-xs text-muted">ids/ips · high · medium</span>
          </div>
          <TrendArea trend={threat} />
        </div>
      </div>

      <div className="panel">
        <div className="px-4 py-3 border-b border-border flex items-baseline justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Branch heatmap</h2>
          <span className="text-xs text-muted">ranked by suspicion score</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Branch</th>
                <th className="text-right px-4 py-2 font-medium">Flows</th>
                <th className="text-right px-4 py-2 font-medium">Blocked</th>
                <th className="text-right px-4 py-2 font-medium">IDS/IPS</th>
                <th className="text-right px-4 py-2 font-medium">High risk</th>
                <th className="text-right px-4 py-2 font-medium">Suspicion</th>
              </tr>
            </thead>
            <tbody>
              {overview.branch_heat.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-muted text-sm">No data yet — collectors haven't ticked in this window.</td></tr>
              )}
              {overview.branch_heat.map((b) => (
                <tr key={b.branch_id} className="border-b border-border last:border-b-0 hover:bg-panel2/40">
                  <td className="px-4 py-2">
                    <Link href={`/branches/${b.branch_id}`} className="text-text hover:text-accent">{b.branch_name}</Link>
                    <div className="text-xs text-muted num">{b.branch_code}</div>
                  </td>
                  <td className="px-4 py-2 text-right num">{fmtNum(b.flows)}</td>
                  <td className="px-4 py-2 text-right num text-danger/90">{fmtNum(b.blocked)}</td>
                  <td className="px-4 py-2 text-right num text-accent">{fmtNum(b.ids_ips)}</td>
                  <td className="px-4 py-2 text-right num text-danger">{fmtNum(b.high_risk)}</td>
                  <td className="px-4 py-2 text-right num">{b.suspicion_score.toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
