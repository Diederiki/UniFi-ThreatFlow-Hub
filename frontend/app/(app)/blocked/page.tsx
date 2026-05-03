"use client";

import { useEffect, useState } from "react";
import { eventsApi, type EventsPage, type FlowEvent, type Top, type Trend } from "@/lib/dashboard";
import { api } from "@/lib/api";
import { TopList } from "@/components/TopList";
import { TrendArea } from "@/components/charts/TrendArea";
import { useTimeframe } from "@/lib/timeframe";
import type { Timeframe } from "@/lib/timeframe";
import { AdvancedFilters, type FilterValues } from "@/components/AdvancedFilters";
import { BLOCKED_FILTERS } from "@/lib/filterDefs";

const blockedApi = {
  topDestinations: (tf: Timeframe, limit = 10) => api<Top>(`/blocked/top-destinations?timeframe=${tf}&limit=${limit}`),
  topClients:      (tf: Timeframe, limit = 10) => api<Top>(`/blocked/top-clients?timeframe=${tf}&limit=${limit}`),
  topPolicies:     (tf: Timeframe, limit = 10) => api<Top>(`/blocked/top-policies?timeframe=${tf}&limit=${limit}`),
  topCountries:    (tf: Timeframe, limit = 10) => api<Top>(`/blocked/top-countries?timeframe=${tf}&limit=${limit}`),
  trend:           (tf: Timeframe) => api<Trend>(`/blocked/trend?timeframe=${tf}`),
};

export default function BlockedPage() {
  const { timeframe } = useTimeframe();
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<FilterValues>({});
  const [data, setData] = useState<EventsPage<FlowEvent> | null>(null);
  const [topDst, setTopDst] = useState<Top | null>(null);
  const [topClt, setTopClt] = useState<Top | null>(null);
  const [topPol, setTopPol] = useState<Top | null>(null);
  const [topCo, setTopCo] = useState<Top | null>(null);
  const [trend, setTrend] = useState<Trend | null>(null);

  useEffect(() => {
    let cancelled = false;
    const apiArgs: Record<string, string> = {};
    for (const [k, v] of Object.entries(filters)) if (v !== undefined && v !== "") apiArgs[k] = String(v);
    Promise.all([
      eventsApi.blocked(timeframe, { ...apiArgs, page, page_size: 50 }),
      blockedApi.topDestinations(timeframe),
      blockedApi.topClients(timeframe),
      blockedApi.topPolicies(timeframe),
      blockedApi.topCountries(timeframe),
      blockedApi.trend(timeframe),
    ]).then(([d, dst, clt, pol, co, tr]) => {
      if (cancelled) return;
      setData(d); setTopDst(dst); setTopClt(clt); setTopPol(pol); setTopCo(co); setTrend(tr);
    });
    return () => { cancelled = true; };
  }, [timeframe, page, JSON.stringify(filters)]);

  useEffect(() => { setPage(1); }, [JSON.stringify(filters)]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Blocked Traffic</h1>
        <p className="text-xs text-muted">~{data?.total_estimate.toLocaleString() ?? "—"} blocked sessions in last {timeframe} · page {page}</p>
      </div>

      <AdvancedFilters defs={BLOCKED_FILTERS} value={filters} onChange={setFilters} storageKey="threatflow.filters.blocked" />

      <div className="panel p-4">
        <div className="flex items-baseline justify-between mb-2">
          <div className="text-xs uppercase text-muted">Blocked trend ({trend?.bucket_label ?? "—"})</div>
        </div>
        <TrendArea trend={trend} height={180} />
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <TopList title="Top destinations" data={topDst} />
        <TopList title="Top clients"      data={topClt} />
        <TopList title="Top policies"     data={topPol} />
        <TopList title="Top countries"    data={topCo} />
      </div>

      <div className="panel overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="text-left px-3 py-2 font-medium">When</th>
              <th className="text-left px-3 py-2 font-medium">Branch</th>
              <th className="text-left px-3 py-2 font-medium">Source</th>
              <th className="text-left px-3 py-2 font-medium">Destination</th>
              <th className="text-left px-3 py-2 font-medium">App</th>
              <th className="text-left px-3 py-2 font-medium">Policy</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-muted text-sm">No blocked sessions in this window.</td></tr>}
            {data?.items.map((e) => (
              <tr key={e.event_id} className="border-b border-border last:border-b-0">
                <td className="px-3 py-2 text-xs text-muted whitespace-nowrap">{new Date(e.event_time).toLocaleTimeString()}</td>
                <td className="px-3 py-2 num text-xs">{e.branch_code}</td>
                <td className="px-3 py-2 num text-xs">{e.source_ip}</td>
                <td className="px-3 py-2 num text-xs">{e.destination_hostname || e.destination_ip}{e.destination_country ? ` · ${e.destination_country}` : ""}</td>
                <td className="px-3 py-2 text-xs">{e.application || "—"}</td>
                <td className="px-3 py-2 text-xs text-muted">{e.policy_name || e.policy_type}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-xs text-muted">
        <button className="btn text-xs" disabled={page === 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>← Prev</button>
        <span>page {page}</span>
        <button className="btn text-xs" disabled={!data?.next_offset} onClick={() => setPage((p) => p + 1)}>Next →</button>
      </div>
    </div>
  );
}
