"use client";

import { useEffect, useState } from "react";
import { eventsApi, topApi, type EventsPage, type FlowEvent, type Top } from "@/lib/dashboard";
import { TopList } from "@/components/TopList";
import { useTimeframe } from "@/lib/timeframe";

export default function BlockedPage() {
  const { timeframe } = useTimeframe();
  const [page, setPage] = useState(1);
  const [data, setData] = useState<EventsPage<FlowEvent> | null>(null);
  const [topDst, setTopDst] = useState<Top | null>(null);
  const [topClt, setTopClt] = useState<Top | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      eventsApi.blocked(timeframe, { page, page_size: 50 }),
      topApi.destinations(timeframe, 10),
      topApi.clients(timeframe, 10),
    ]).then(([d, dst, clt]) => { if (cancelled) return; setData(d); setTopDst(dst); setTopClt(clt); });
    return () => { cancelled = true; };
  }, [timeframe, page]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Blocked Traffic</h1>
        <p className="text-xs text-muted">~{data?.total_estimate.toLocaleString() ?? "—"} blocked sessions in last {timeframe} · page {page}</p>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <TopList title="Top blocked destinations" data={topDst} />
        <TopList title="Top blocked clients"      data={topClt} />
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
