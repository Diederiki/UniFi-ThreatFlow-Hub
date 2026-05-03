"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { suspicionApi, type SuspiciousBranch, type SuspiciousClient, type SuspiciousDestination } from "@/lib/suspicion";
import type { Trend } from "@/lib/dashboard";
import { TrendArea } from "@/components/charts/TrendArea";
import { useTimeframe } from "@/lib/timeframe";

export default function SuspicionPage() {
  const { timeframe } = useTimeframe();
  const [branches, setBranches] = useState<SuspiciousBranch[]>([]);
  const [clients, setClients] = useState<SuspiciousClient[]>([]);
  const [destinations, setDestinations] = useState<SuspiciousDestination[]>([]);
  const [trend, setTrend] = useState<Trend | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function reload() {
      const [b, c, d, t] = await Promise.all([
        suspicionApi.branches(timeframe, 20),
        suspicionApi.clients(timeframe, 20),
        suspicionApi.destinations(timeframe, 20),
        suspicionApi.trend(timeframe),
      ]);
      if (cancelled) return;
      setBranches(b.items); setClients(c.items); setDestinations(d.items); setTrend(t);
    }
    reload();
    const id = setInterval(reload, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [timeframe]);

  const maxBranchScore = Math.max(1, ...branches.map((b) => b.score));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">Suspicion Score</h1>
        <p className="text-xs text-muted">Weighted score per blueprint § Suspicion · weights configurable in <Link href="/settings" className="text-accent hover:underline">Settings</Link> · last {timeframe}</p>
      </div>

      <div className="panel p-4">
        <div className="text-xs text-muted uppercase mb-2">Aggregate suspicion trend</div>
        <TrendArea trend={trend} height={180} />
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="panel">
          <div className="px-4 py-3 border-b border-border">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Top suspicious branches</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase tracking-wide text-muted border-b border-border">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">Branch</th>
                  <th className="text-right px-3 py-2 font-medium">Score</th>
                </tr>
              </thead>
              <tbody>
                {branches.map((b) => (
                  <tr key={b.branch_id} className="border-b border-border last:border-b-0">
                    <td className="px-3 py-2">
                      <Link href={`/branches/${b.branch_id}`} className="hover:text-accent">{b.branch_name}</Link>
                      <div className="text-xs text-muted num">{b.branch_code} · {b.high_risk}h / {b.medium_risk}m / {b.low_risk}l · {b.blocked} blocked / {b.ids_ips} ids</div>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="num">{b.score.toFixed(0)}</div>
                      <div className="h-1 w-24 ml-auto mt-1 bg-panel2 rounded overflow-hidden">
                        <div className="h-full bg-danger/50" style={{ width: `${(b.score / maxBranchScore) * 100}%` }} />
                      </div>
                    </td>
                  </tr>
                ))}
                {branches.length === 0 && <tr><td colSpan={2} className="px-4 py-8 text-center text-muted text-sm">No branches scored yet.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel">
          <div className="px-4 py-3 border-b border-border">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Top suspicious clients</h2>
          </div>
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted border-b border-border">
              <tr>
                <th className="text-left px-3 py-2 font-medium">Client</th>
                <th className="text-right px-3 py-2 font-medium">Score</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((c) => (
                <tr key={c.client_ip} className="border-b border-border last:border-b-0">
                  <td className="px-3 py-2 num">{c.client_ip}<div className="text-xs text-muted">{c.branch_code} · {c.threats} threats / {c.blocked} blocked</div></td>
                  <td className="px-3 py-2 text-right num">{c.score.toFixed(0)}</td>
                </tr>
              ))}
              {clients.length === 0 && <tr><td colSpan={2} className="px-4 py-8 text-center text-muted text-sm">—</td></tr>}
            </tbody>
          </table>
        </div>

        <div className="panel">
          <div className="px-4 py-3 border-b border-border">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Top suspicious destinations</h2>
          </div>
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted border-b border-border">
              <tr>
                <th className="text-left px-3 py-2 font-medium">Destination</th>
                <th className="text-right px-3 py-2 font-medium">Score</th>
              </tr>
            </thead>
            <tbody>
              {destinations.map((d) => (
                <tr key={d.destination_ip} className="border-b border-border last:border-b-0">
                  <td className="px-3 py-2">
                    <div className="num text-xs">{d.destination_hostname || d.destination_ip}</div>
                    <div className="text-xs text-muted num">{d.destination_ip}{d.destination_country ? ` · ${d.destination_country}` : ""} · {d.threats} threats</div>
                  </td>
                  <td className="px-3 py-2 text-right num">{d.score.toFixed(0)}</td>
                </tr>
              ))}
              {destinations.length === 0 && <tr><td colSpan={2} className="px-4 py-8 text-center text-muted text-sm">—</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
