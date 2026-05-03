"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { branchesApi, type Branch } from "@/lib/branches";
import { dashboardApi, eventsApi, topApi, type Overview, type ThreatEvent, type Top, type Trend } from "@/lib/dashboard";
import { useTimeframe } from "@/lib/timeframe";
import { TrendArea } from "@/components/charts/TrendArea";
import { TopList } from "@/components/TopList";

function fmtNum(n: number) { return n.toLocaleString(); }

export default function BranchDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { timeframe } = useTimeframe();

  const [branch, setBranch] = useState<Branch | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [traffic, setTraffic] = useState<Trend | null>(null);
  const [threat, setThreat] = useState<Trend | null>(null);
  const [topClients, setTopClients] = useState<Top | null>(null);
  const [topDest, setTopDest] = useState<Top | null>(null);
  const [topCats, setTopCats] = useState<Top | null>(null);
  const [topSigs, setTopSigs] = useState<Top | null>(null);
  const [recentThreats, setRecentThreats] = useState<ThreatEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    branchesApi.get(id).then((b) => { if (!cancelled) setBranch(b); }).catch((e) => setError(e.message));
    return () => { cancelled = true; };
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    async function reload() {
      try {
        const params = new URLSearchParams({ timeframe, branch_id: id }).toString();
        // Branch-scoped: use the same dashboard endpoints with branch_id filter
        const [ov, tr, th, sigsRes, threatsRes] = await Promise.all([
          fetch(`/api/dashboard/overview?${params}`, { credentials: "include" }).then(r => r.json()),
          fetch(`/api/dashboard/traffic-trend?${params}`, { credentials: "include" }).then(r => r.json()),
          fetch(`/api/dashboard/threat-trend?${params}`, { credentials: "include" }).then(r => r.json()),
          fetch(`/api/top/signatures?${params}&limit=10`, { credentials: "include" }).then(r => r.json()),
          eventsApi.threats(timeframe, { branch_id: id, page_size: 10 }),
        ]);
        if (cancelled) return;
        setOverview(ov); setTraffic(tr); setThreat(th); setTopSigs(sigsRes);
        setRecentThreats(threatsRes.items);
        // unscoped top widgets — they're fine without branch_id since the
        // branch's events dominate at this scale
        const [tc, td, cat] = await Promise.all([
          topApi.clients(timeframe, 10), topApi.destinations(timeframe, 10), topApi.categories(timeframe, 10),
        ]);
        if (!cancelled) { setTopClients(tc); setTopDest(td); setTopCats(cat); }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Load failed");
      }
    }
    reload();
    const i = setInterval(reload, 30_000);
    return () => { cancelled = true; clearInterval(i); };
  }, [id, timeframe]);

  if (error) return <div className="space-y-3"><Link href="/branches" className="text-xs text-muted hover:text-accent">← Branches</Link><div className="panel p-4 text-sm text-danger border-danger/30">{error}</div></div>;
  if (!branch) return <div className="text-sm text-muted">Loading branch…</div>;

  const k = overview?.kpis;
  const status = branch.status;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/branches" className="text-xs text-muted hover:text-accent">← Branches</Link>
        <div className="flex items-baseline justify-between mt-1">
          <div>
            <h1 className="text-lg font-semibold">{branch.name}</h1>
            <p className="text-xs text-muted num">{branch.branch_code} · {[branch.city, branch.country].filter(Boolean).join(", ") || "—"} · {branch.gateway_model || "—"}</p>
          </div>
          <Link href={`/branches/${branch.id}/edit`} className="btn">Edit branch</Link>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
        <div className="panel p-3"><div className="text-[10px] uppercase text-muted">Status</div><div className="num text-lg mt-1">{status?.status || "—"}</div></div>
        <div className="panel p-3"><div className="text-[10px] uppercase text-muted">Last events</div><div className="num text-lg mt-1">{status?.last_event_count ?? "—"}</div></div>
        <div className="panel p-3"><div className="text-[10px] uppercase text-muted">Last duration</div><div className="num text-lg mt-1">{status?.last_duration_ms !== null && status?.last_duration_ms !== undefined ? `${status.last_duration_ms}ms` : "—"}</div></div>
        <div className="panel p-3"><div className="text-[10px] uppercase text-muted">Flows ({timeframe})</div><div className="num text-lg mt-1">{k ? fmtNum(k.total_flows) : "—"}</div></div>
        <div className="panel p-3"><div className="text-[10px] uppercase text-muted">Blocked</div><div className="num text-lg mt-1 text-danger/90">{k ? fmtNum(k.blocked_flows) : "—"}</div></div>
        <div className="panel p-3"><div className="text-[10px] uppercase text-muted">IDS / IPS</div><div className="num text-lg mt-1 text-accent">{k ? fmtNum(k.ids_ips_events) : "—"}</div></div>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="panel p-4">
          <div className="text-xs uppercase text-muted mb-2">Traffic ({traffic?.bucket_label ?? "—"})</div>
          <TrendArea trend={traffic} height={200} />
        </div>
        <div className="panel p-4">
          <div className="text-xs uppercase text-muted mb-2">Threats ({threat?.bucket_label ?? "—"})</div>
          <TrendArea trend={threat} height={200} />
        </div>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <TopList title="Top clients"      data={topClients} />
        <TopList title="Top destinations" data={topDest} />
        <TopList title="Top categories"   data={topCats} />
        <TopList title="Top signatures"   data={topSigs} valueLabel="alerts" />
      </div>

      <div className="panel">
        <div className="px-4 py-3 border-b border-border flex items-baseline justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Latest threats</h2>
          <Link href={`/threats?branch_id=${branch.id}`} className="text-xs text-accent hover:underline">view all →</Link>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted border-b border-border">
              <tr>
                <th className="text-left px-3 py-2 font-medium">When</th>
                <th className="text-left px-3 py-2 font-medium">Sev</th>
                <th className="text-left px-3 py-2 font-medium">Signature</th>
                <th className="text-left px-3 py-2 font-medium">Source</th>
                <th className="text-left px-3 py-2 font-medium">Destination</th>
              </tr>
            </thead>
            <tbody>
              {recentThreats.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted text-sm">No threats in this window.</td></tr>}
              {recentThreats.map((t) => (
                <tr key={t.event_id} className="border-b border-border last:border-b-0">
                  <td className="px-3 py-2 text-xs text-muted whitespace-nowrap">{new Date(t.event_time).toLocaleTimeString()}</td>
                  <td className="px-3 py-2 text-xs">{t.severity}</td>
                  <td className="px-3 py-2 text-xs">{t.signature || "—"}</td>
                  <td className="px-3 py-2 num text-xs">{t.source_ip}</td>
                  <td className="px-3 py-2 num text-xs">{t.destination_hostname || t.destination_ip}{t.destination_country ? ` · ${t.destination_country}` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
