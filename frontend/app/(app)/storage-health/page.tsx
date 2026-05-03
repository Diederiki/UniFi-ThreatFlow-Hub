"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type TableHealth = {
  name: string;
  rows: number;
  bytes_on_disk: number;
  bytes_uncompressed: number;
  compression_ratio: number | null;
  parts: number;
  oldest_event: string | null;
  newest_event: string | null;
};

type StorageHealth = {
  clickhouse_ok: boolean;
  raw_flow_events: TableHealth | null;
  raw_threat_events: TableHealth | null;
  rollup_1m: TableHealth | null;
  rollup_5m: TableHealth | null;
  rollup_15m: TableHealth | null;
  rollup_1h: TableHealth | null;
  rollup_1d: TableHealth | null;
  failed_inserts_30d: number;
  rollup_freshness_1m_seconds: number | null;
  events_per_day_estimate: number | null;
};

type Retention = { items: { table: string; ttl_days: number }[] };

function fmtBytes(n: number): string {
  if (n === 0) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB", "PB"];
  const e = Math.min(Math.floor(Math.log(n) / Math.log(1024)), u.length - 1);
  return `${(n / Math.pow(1024, e)).toFixed(2)} ${u[e]}`;
}

function fmtNum(n: number): string {
  return n.toLocaleString();
}

function fmtRel(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString();
}

const TABLES: (keyof Omit<StorageHealth, "clickhouse_ok" | "failed_inserts_30d" | "rollup_freshness_1m_seconds" | "events_per_day_estimate">)[] = [
  "raw_flow_events",
  "raw_threat_events",
  "rollup_1m",
  "rollup_5m",
  "rollup_15m",
  "rollup_1h",
  "rollup_1d",
];

export default function StorageHealthPage() {
  const [data, setData] = useState<StorageHealth | null>(null);
  const [retention, setRetention] = useState<Retention | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    try {
      const [h, r] = await Promise.all([
        api<StorageHealth>("/storage/health"),
        api<Retention>("/storage/retention"),
      ]);
      setData(h);
      setRetention(r);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    }
  }

  useEffect(() => {
    reload();
    const i = setInterval(reload, 30_000);
    return () => clearInterval(i);
  }, []);

  if (error) {
    return <div className="panel p-4 text-sm text-danger border-danger/30">{error}</div>;
  }
  if (!data) {
    return <div className="text-sm text-muted">Loading…</div>;
  }

  const ttlByTable = Object.fromEntries((retention?.items ?? []).map((i) => [i.table, i.ttl_days]));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">Storage Health</h1>
        <p className="text-xs text-muted">
          ClickHouse: {data.clickhouse_ok ? <span className="text-success">healthy</span> : <span className="text-danger">unreachable</span>}
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="panel p-4">
          <div className="text-xs uppercase text-muted">Failed inserts (30d)</div>
          <div className="text-2xl num mt-1">{fmtNum(data.failed_inserts_30d)}</div>
        </div>
        <div className="panel p-4">
          <div className="text-xs uppercase text-muted">1m rollup freshness</div>
          <div className="text-2xl num mt-1">
            {data.rollup_freshness_1m_seconds === null ? "—" : `${data.rollup_freshness_1m_seconds}s`}
          </div>
        </div>
        <div className="panel p-4">
          <div className="text-xs uppercase text-muted">Events / day (est)</div>
          <div className="text-2xl num mt-1">{data.events_per_day_estimate === null ? "—" : fmtNum(data.events_per_day_estimate)}</div>
        </div>
        <div className="panel p-4">
          <div className="text-xs uppercase text-muted">Tables tracked</div>
          <div className="text-2xl num mt-1">{TABLES.length}</div>
        </div>
      </div>

      <div className="panel overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="text-left px-4 py-2 font-medium">Table</th>
              <th className="text-right px-4 py-2 font-medium">Rows</th>
              <th className="text-right px-4 py-2 font-medium">On disk</th>
              <th className="text-right px-4 py-2 font-medium">Uncompressed</th>
              <th className="text-right px-4 py-2 font-medium">Ratio</th>
              <th className="text-right px-4 py-2 font-medium">Parts</th>
              <th className="text-left px-4 py-2 font-medium">Oldest</th>
              <th className="text-left px-4 py-2 font-medium">Newest</th>
              <th className="text-right px-4 py-2 font-medium">TTL (days)</th>
            </tr>
          </thead>
          <tbody>
            {TABLES.map((t) => {
              const th = data[t] as TableHealth | null;
              const ttl = ttlByTable[t] ?? "—";
              return (
                <tr key={t} className="border-b border-border last:border-b-0">
                  <td className="px-4 py-2 font-mono text-xs">{t}</td>
                  <td className="px-4 py-2 text-right num">{th ? fmtNum(th.rows) : "—"}</td>
                  <td className="px-4 py-2 text-right num">{th ? fmtBytes(th.bytes_on_disk) : "—"}</td>
                  <td className="px-4 py-2 text-right num text-muted">{th ? fmtBytes(th.bytes_uncompressed) : "—"}</td>
                  <td className="px-4 py-2 text-right num">{th?.compression_ratio !== undefined && th?.compression_ratio !== null ? `${th.compression_ratio}×` : "—"}</td>
                  <td className="px-4 py-2 text-right num text-muted">{th ? fmtNum(th.parts) : "—"}</td>
                  <td className="px-4 py-2 text-xs text-muted">{th ? fmtRel(th.oldest_event) : "—"}</td>
                  <td className="px-4 py-2 text-xs text-muted">{th ? fmtRel(th.newest_event) : "—"}</td>
                  <td className="px-4 py-2 text-right num">{ttl}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-muted">
        TTL editing UI lives in <span className="text-text">Settings → Retention</span> (Phase 7).
        For now the schema defaults are 90 / 180 / 180 / 365 / 365 / 730 / 1825 days.
      </p>
    </div>
  );
}
