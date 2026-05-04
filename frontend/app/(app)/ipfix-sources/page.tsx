"use client";

import { useEffect, useState } from "react";

type IpfixSource = {
  branch_id: string | null;
  branch_code: string;
  branch_name: string;
  last_event_at: string | null;
  rows_5m: number;
  rows_1h: number;
  rows_24h: number;
  bytes_24h: number;
  distinct_destinations_24h: number;
  is_known_branch: boolean;
};

type Resp = {
  items: IpfixSource[];
  total_known_branches: number;
  sending_now: number;
};

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const u = ["KB", "MB", "GB", "TB"];
  let v = n / 1024, i = 0;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${u[i]}`;
}

function fmtAgo(iso: string | null): string {
  if (!iso) return "—";
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 0) return "now";
  if (ms < 60_000) return `${Math.round(ms / 1000)}s ago`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m ago`;
  if (ms < 86_400_000) return `${Math.round(ms / 3_600_000)}h ago`;
  return `${Math.round(ms / 86_400_000)}d ago`;
}

function statusFor(r: IpfixSource): { dot: string; text: string; cls: string } {
  if (r.rows_5m > 0)
    return { dot: "🟢", text: "live", cls: "text-success" };
  if (r.rows_1h > 0)
    return { dot: "🟡", text: "stale", cls: "text-warn" };
  return { dot: "⚪", text: "silent", cls: "text-muted" };
}

export default function IpfixSourcesPage() {
  const [data, setData] = useState<Resp | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    try {
      const res = await fetch("/api/ipfix/sources", { credentials: "include" });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      setData(await res.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    reload();
    const id = setInterval(reload, 10_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold">IPFIX Sources</h1>
          <p className="text-xs text-muted">
            Per-branch flow-export status from the UDM gateways. Auto-refreshes every 10s.
          </p>
        </div>
        {data && (
          <div className="text-xs text-muted">
            <span className="text-success">●</span> {data.sending_now} live ·{" "}
            {data.total_known_branches} sending in last 24h
          </div>
        )}
      </div>

      {error && (
        <div className="panel p-3 text-sm text-danger">Failed to load: {error}</div>
      )}

      <div className="panel overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="text-left  px-3 py-2 font-medium">Status</th>
              <th className="text-left  px-3 py-2 font-medium">Branch</th>
              <th className="text-right px-3 py-2 font-medium">Last seen</th>
              <th className="text-right px-3 py-2 font-medium">Rows / 5m</th>
              <th className="text-right px-3 py-2 font-medium">Rows / 1h</th>
              <th className="text-right px-3 py-2 font-medium">Rows / 24h</th>
              <th className="text-right px-3 py-2 font-medium">Traffic / 24h</th>
              <th className="text-right px-3 py-2 font-medium">Distinct dest / 24h</th>
            </tr>
          </thead>
          <tbody>
            {!data && (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-muted text-sm">Loading…</td></tr>
            )}
            {data && data.items.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-muted text-sm">
                No IPFIX flows received yet. Configure the UDMs to export to <span className="num">51.195.82.50:2055</span>.
              </td></tr>
            )}
            {data?.items.map((r) => {
              const s = statusFor(r);
              return (
                <tr key={`${r.branch_id ?? r.branch_code}`}
                    className="border-b border-border last:border-b-0 hover:bg-panel2/40">
                  <td className="px-3 py-2">
                    <span className={`text-xs ${s.cls}`}>{s.dot} {s.text}</span>
                  </td>
                  <td className="px-3 py-2">
                    <div className="text-sm">{r.branch_name}</div>
                    <div className="text-[11px] text-muted num">
                      {r.branch_code}{!r.is_known_branch && " · WAN-IP unmapped"}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right text-xs num">{fmtAgo(r.last_event_at)}</td>
                  <td className="px-3 py-2 text-right num">{r.rows_5m.toLocaleString()}</td>
                  <td className="px-3 py-2 text-right num">{r.rows_1h.toLocaleString()}</td>
                  <td className="px-3 py-2 text-right num">{r.rows_24h.toLocaleString()}</td>
                  <td className="px-3 py-2 text-right num">{fmtBytes(r.bytes_24h)}</td>
                  <td className="px-3 py-2 text-right num">{r.distinct_destinations_24h.toLocaleString()}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
