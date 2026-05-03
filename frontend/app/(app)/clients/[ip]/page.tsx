"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useTimeframe } from "@/lib/timeframe";
import type { ClientSummary, EventsPage, FlowEvent, ThreatEvent } from "@/lib/dashboard";

function fmtBytes(n: number): string {
  if (!n) return "0";
  const u = ["B", "KB", "MB", "GB", "TB"];
  const e = Math.min(Math.floor(Math.log(n) / Math.log(1024)), u.length - 1);
  return `${(n / Math.pow(1024, e)).toFixed(1)} ${u[e]}`;
}

export default function ClientDetailPage() {
  const { ip } = useParams<{ ip: string }>();
  const { timeframe } = useTimeframe();
  const [summary, setSummary] = useState<ClientSummary | null>(null);
  const [flows, setFlows] = useState<EventsPage<FlowEvent> | null>(null);
  const [threats, setThreats] = useState<EventsPage<ThreatEvent> | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api<ClientSummary>(`/clients/${ip}?timeframe=${timeframe}`),
      api<EventsPage<FlowEvent>>(`/clients/${ip}/flows?timeframe=${timeframe}&page_size=50`),
      api<EventsPage<ThreatEvent>>(`/clients/${ip}/threats?timeframe=${timeframe}&page_size=20`),
    ]).then(([s, f, t]) => {
      if (cancelled) return;
      setSummary(s); setFlows(f); setThreats(t);
    });
    return () => { cancelled = true; };
  }, [ip, timeframe]);

  return (
    <div className="space-y-6">
      <div>
        <Link href="/clients" className="text-xs text-muted hover:text-accent">← Clients</Link>
        <h1 className="text-lg font-semibold num mt-1">{ip}</h1>
        {summary && <p className="text-xs text-muted">branch {summary.branch_code} · last {timeframe}</p>}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div className="panel p-3"><div className="text-[10px] uppercase text-muted">Flows</div><div className="num text-lg mt-1">{summary?.flows.toLocaleString() ?? "—"}</div></div>
        <div className="panel p-3"><div className="text-[10px] uppercase text-muted">Blocked</div><div className="num text-lg mt-1 text-danger/90">{summary?.blocked.toLocaleString() ?? "—"}</div></div>
        <div className="panel p-3"><div className="text-[10px] uppercase text-muted">Threats</div><div className="num text-lg mt-1 text-accent">{summary?.threats.toLocaleString() ?? "—"}</div></div>
        <div className="panel p-3"><div className="text-[10px] uppercase text-muted">Up</div><div className="num text-lg mt-1">{fmtBytes(summary?.bytes_up ?? 0)}</div></div>
        <div className="panel p-3"><div className="text-[10px] uppercase text-muted">Down</div><div className="num text-lg mt-1">{fmtBytes(summary?.bytes_down ?? 0)}</div></div>
      </div>

      <div className="panel">
        <div className="px-4 py-3 border-b border-border flex items-baseline justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Recent threats</h2>
          <span className="text-xs text-muted">latest 20</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted border-b border-border">
              <tr>
                <th className="text-left px-3 py-2 font-medium">When</th>
                <th className="text-left px-3 py-2 font-medium">Signature</th>
                <th className="text-left px-3 py-2 font-medium">Sev</th>
                <th className="text-left px-3 py-2 font-medium">Destination</th>
                <th className="text-left px-3 py-2 font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {threats?.items.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted text-sm">No threats from this client.</td></tr>}
              {threats?.items.map((t) => (
                <tr key={t.event_id} className="border-b border-border last:border-b-0">
                  <td className="px-3 py-2 text-xs text-muted whitespace-nowrap">{new Date(t.event_time).toLocaleString()}</td>
                  <td className="px-3 py-2 text-xs">{t.signature || "—"}</td>
                  <td className="px-3 py-2 text-xs">{t.severity}</td>
                  <td className="px-3 py-2 num text-xs">{t.destination_hostname || t.destination_ip}{t.destination_country ? ` · ${t.destination_country}` : ""}</td>
                  <td className="px-3 py-2 text-xs">{t.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <div className="px-4 py-3 border-b border-border">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Recent flows ({flows?.items.length ?? 0})</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted border-b border-border">
              <tr>
                <th className="text-left px-3 py-2 font-medium">When</th>
                <th className="text-left px-3 py-2 font-medium">Action</th>
                <th className="text-left px-3 py-2 font-medium">Destination</th>
                <th className="text-left px-3 py-2 font-medium">App</th>
                <th className="text-left px-3 py-2 font-medium">Category</th>
                <th className="text-right px-3 py-2 font-medium">Bytes ↑/↓</th>
              </tr>
            </thead>
            <tbody>
              {flows?.items.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-muted text-sm">No flows.</td></tr>}
              {flows?.items.map((e) => (
                <tr key={e.event_id} className="border-b border-border last:border-b-0">
                  <td className="px-3 py-2 text-xs text-muted whitespace-nowrap">{new Date(e.event_time).toLocaleTimeString()}</td>
                  <td className="px-3 py-2 text-xs">{e.action}</td>
                  <td className="px-3 py-2 num text-xs">{e.destination_hostname || e.destination_ip}</td>
                  <td className="px-3 py-2 text-xs">{e.application || "—"}</td>
                  <td className="px-3 py-2 text-xs text-muted">{e.application_category || "—"}</td>
                  <td className="px-3 py-2 text-right num text-xs text-muted">{fmtBytes(e.bytes_up)} / {fmtBytes(e.bytes_down)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
