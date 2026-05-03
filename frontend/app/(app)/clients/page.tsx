"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useTimeframe } from "@/lib/timeframe";
import { AdvancedFilters, type FilterValues } from "@/components/AdvancedFilters";
import { CLIENT_FILTERS } from "@/lib/filterDefs";
import { api } from "@/lib/api";
import type { ClientList } from "@/lib/dashboard";

function fmtBytes(n: number): string {
  if (!n) return "0";
  const u = ["B", "KB", "MB", "GB", "TB"];
  const e = Math.min(Math.floor(Math.log(n) / Math.log(1024)), u.length - 1);
  return `${(n / Math.pow(1024, e)).toFixed(1)} ${u[e]}`;
}

export default function ClientsPage() {
  const { timeframe } = useTimeframe();
  const [data, setData] = useState<ClientList | null>(null);
  const [filters, setFilters] = useState<FilterValues>({});

  useEffect(() => {
    let cancelled = false;
    const id = setTimeout(() => {
      const params = new URLSearchParams({ timeframe, limit: "100" });
      for (const [k, v] of Object.entries(filters)) if (v !== undefined && v !== "" && v !== 0) params.set(k, String(v));
      api<ClientList>(`/clients?${params.toString()}`).then((d) => { if (!cancelled) setData(d); });
    }, 200);
    return () => { cancelled = true; clearTimeout(id); };
  }, [timeframe, JSON.stringify(filters)]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Clients</h1>
        <p className="text-xs text-muted">{data?.items.length ?? "—"} clients seen in last {timeframe}</p>
      </div>

      <AdvancedFilters defs={CLIENT_FILTERS} value={filters} onChange={setFilters} storageKey="threatflow.filters.clients" />

      <div className="panel overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="text-left px-3 py-2 font-medium">Client</th>
              <th className="text-left px-3 py-2 font-medium">Branch</th>
              <th className="text-right px-3 py-2 font-medium">Flows</th>
              <th className="text-right px-3 py-2 font-medium">Blocked</th>
              <th className="text-right px-3 py-2 font-medium">Threats</th>
              <th className="text-right px-3 py-2 font-medium">Up</th>
              <th className="text-right px-3 py-2 font-medium">Down</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.length === 0 && <tr><td colSpan={7} className="px-4 py-8 text-center text-muted text-sm">No clients matched.</td></tr>}
            {data?.items.map((c) => (
              <tr key={c.client_ip} className="border-b border-border last:border-b-0 hover:bg-panel2/40">
                <td className="px-3 py-2 num">
                  <Link href={`/clients/${encodeURIComponent(c.client_ip)}`} className="hover:text-accent">{c.client_ip}</Link>
                </td>
                <td className="px-3 py-2 num text-xs text-muted">{c.branch_code}</td>
                <td className="px-3 py-2 text-right num">{c.flows.toLocaleString()}</td>
                <td className="px-3 py-2 text-right num text-danger/90">{c.blocked.toLocaleString()}</td>
                <td className="px-3 py-2 text-right num text-accent">{c.threats.toLocaleString()}</td>
                <td className="px-3 py-2 text-right num text-muted">{fmtBytes(c.bytes_up)}</td>
                <td className="px-3 py-2 text-right num text-muted">{fmtBytes(c.bytes_down)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
