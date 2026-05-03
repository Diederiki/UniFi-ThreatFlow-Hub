"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useTimeframe } from "@/lib/timeframe";
import type { EventsPage, FlowEvent } from "@/lib/dashboard";

type DestSummary = {
  destination_ip: string;
  hostname: string | null;
  country: string | null;
  flows: number;
  blocked: number;
  threats: number;
  unique_clients: number;
};

async function fetchDestSummary(ip: string, tf: string): Promise<DestSummary> {
  // Backend has no dedicated endpoint yet — derive client-side via /api/threats and /api/blocked
  // count by destination_ip filter. Simpler: just expose a quick query through /clients-style.
  // For now we approximate by querying threats and blocked separately.
  const params = new URLSearchParams({ timeframe: tf, destination_ip: ip, page_size: "1" }).toString();
  const [threats, blocked] = await Promise.all([
    api<EventsPage<FlowEvent>>(`/threats?${params}`),
    api<EventsPage<FlowEvent>>(`/blocked?${new URLSearchParams({ timeframe: tf, page_size: "1" }).toString()}`),
  ]);
  return {
    destination_ip: ip,
    hostname: threats.items[0]?.destination_hostname ?? null,
    country: threats.items[0]?.destination_country ?? null,
    flows: threats.total_estimate,
    blocked: blocked.total_estimate,
    threats: threats.total_estimate,
    unique_clients: 0,
  };
}

export default function DestinationDetailPage() {
  const { ip } = useParams<{ ip: string }>();
  const { timeframe } = useTimeframe();
  const [summary, setSummary] = useState<DestSummary | null>(null);
  const [recent, setRecent] = useState<FlowEvent[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function reload() {
      try {
        const [s, r] = await Promise.all([
          fetchDestSummary(ip, timeframe),
          api<EventsPage<FlowEvent>>(`/threats?${new URLSearchParams({ timeframe, destination_ip: ip, page_size: "30" }).toString()}`),
        ]);
        if (cancelled) return;
        setSummary(s);
        setRecent(r.items);
      } catch {
        // non-fatal
      }
    }
    reload();
    return () => { cancelled = true; };
  }, [ip, timeframe]);

  return (
    <div className="space-y-6">
      <div>
        <Link href="/destinations" className="text-xs text-muted hover:text-accent">← Destinations</Link>
        <h1 className="text-lg font-semibold num mt-1">{ip}</h1>
        {summary?.hostname && <p className="text-xs text-muted">{summary.hostname} · {summary.country ?? "—"}</p>}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div className="panel p-3"><div className="text-[10px] uppercase text-muted">Threat events</div><div className="num text-lg mt-1 text-accent">{summary?.threats?.toLocaleString() ?? "—"}</div></div>
        <div className="panel p-3"><div className="text-[10px] uppercase text-muted">Country</div><div className="num text-lg mt-1">{summary?.country ?? "—"}</div></div>
        <div className="panel p-3"><div className="text-[10px] uppercase text-muted">Hostname</div><div className="text-sm mt-1 truncate">{summary?.hostname ?? "—"}</div></div>
      </div>

      <div className="panel">
        <div className="px-4 py-3 border-b border-border">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Recent threat events to this destination</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted border-b border-border">
              <tr>
                <th className="text-left px-3 py-2 font-medium">When</th>
                <th className="text-left px-3 py-2 font-medium">Branch</th>
                <th className="text-left px-3 py-2 font-medium">Source</th>
                <th className="text-left px-3 py-2 font-medium">Action</th>
                <th className="text-left px-3 py-2 font-medium">Sev</th>
              </tr>
            </thead>
            <tbody>
              {recent.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted text-sm">No threat events to this destination in {timeframe}.</td></tr>}
              {recent.map((e) => (
                <tr key={e.event_id} className="border-b border-border last:border-b-0">
                  <td className="px-3 py-2 text-xs text-muted whitespace-nowrap">{new Date(e.event_time).toLocaleTimeString()}</td>
                  <td className="px-3 py-2 num text-xs">{e.branch_code}</td>
                  <td className="px-3 py-2 num text-xs">{e.source_ip}</td>
                  <td className="px-3 py-2 text-xs">{e.action}</td>
                  <td className="px-3 py-2 text-xs">{e.severity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
