"use client";

import { useEffect, useRef, useState } from "react";
import { observabilityApi, type HostMetrics, type ProcessRow } from "@/lib/observability";
import { Ring } from "@/components/charts/Ring";

function fmtBytes(n: number): string {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  const e = Math.min(Math.floor(Math.log(n) / Math.log(1024)), u.length - 1);
  return `${(n / Math.pow(1024, e)).toFixed(2)} ${u[e]}`;
}

function fmtRate(n: number): string {
  if (n < 1024) return `${n.toFixed(0)} B/s`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB/s`;
  return `${(n / 1024 ** 2).toFixed(2)} MB/s`;
}

const REFRESH_MS = 2000;

export default function OperationsPage() {
  const [host, setHost] = useState<HostMetrics | null>(null);
  const [procs, setProcs] = useState<ProcessRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const procTickRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const h = await observabilityApi.host();
        if (cancelled) return;
        setHost(h);
        setError(null);
        // refresh process table at ~10× the host rate (every 20s)
        if (procTickRef.current % 10 === 0) {
          const p = await observabilityApi.processes(15);
          if (!cancelled) setProcs(p.items);
        }
        procTickRef.current += 1;
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Load failed");
      }
    }
    tick();
    const id = setInterval(tick, REFRESH_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <div>
          <span className="inline-block text-[10px] uppercase tracking-widest px-1.5 py-0.5 rounded border border-danger/40 text-danger/90 bg-danger/10">Operations</span>
          <h1 className="text-2xl font-semibold mt-2">Observability</h1>
          <p className="text-xs text-muted">Live health probes for every operational subsystem · refreshes every {REFRESH_MS}ms</p>
        </div>
        <div className="text-xs">
          <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-success/40 text-success bg-success/10">
            <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
            Live · {REFRESH_MS} ms
          </span>
        </div>
      </div>

      {error && <div className="panel p-4 text-sm text-danger border-danger/30">{error}</div>}

      <div>
        <div className="text-[10px] uppercase tracking-widest text-muted mb-2">Live host monitors</div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="panel p-5">
            <div className="flex items-center justify-between text-xs uppercase text-muted mb-3">
              <span>CPU</span><span className="text-muted/60">⚙</span>
            </div>
            <Ring
              percent={host?.cpu.percent ?? 0}
              label={`${(host?.cpu.percent ?? 0).toFixed(0)}%`}
              sublabel={host ? `${host.cpu.cores} cores` : "—"}
              color="#22d3ee"
            />
          </div>

          <div className="panel p-5">
            <div className="flex items-center justify-between text-xs uppercase text-muted mb-3">
              <span>Memory</span><span className="text-muted/60">▭</span>
            </div>
            <Ring
              percent={host?.memory.percent ?? 0}
              label={`${(host?.memory.percent ?? 0).toFixed(0)}%`}
              sublabel={host ? `${fmtBytes(host.memory.used)} / ${fmtBytes(host.memory.total)}` : "—"}
              color="#7c3aed"
            />
          </div>

          <div className="panel p-5">
            <div className="flex items-center justify-between text-xs uppercase text-muted mb-3">
              <span>Disk</span><span className="text-muted/60">⌘</span>
            </div>
            <Ring
              percent={host?.disk.percent ?? 0}
              label={`${(host?.disk.percent ?? 0).toFixed(0)}%`}
              sublabel={host ? `${fmtBytes(host.disk.used)} / ${fmtBytes(host.disk.total)}` : "—"}
              color={(host?.disk.percent ?? 0) > 85 ? "#ef4444" : (host?.disk.percent ?? 0) > 70 ? "#f59e0b" : "#22c55e"}
            />
          </div>

          <div className="panel p-5">
            <div className="flex items-center justify-between text-xs uppercase text-muted mb-3">
              <span>Network</span><span className="text-muted/60">↕</span>
            </div>
            <Ring
              percent={Math.min(100, ((host?.network.rx_bytes_per_s ?? 0) + (host?.network.tx_bytes_per_s ?? 0)) / (1024 * 1024) * 10)}
              label={fmtRate((host?.network.rx_bytes_per_s ?? 0) + (host?.network.tx_bytes_per_s ?? 0))}
              sublabel={host ? `↓ ${fmtRate(host.network.rx_bytes_per_s)} · ↑ ${fmtRate(host.network.tx_bytes_per_s)}` : "—"}
              color="#22d3ee"
            />
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="px-4 py-3 border-b border-border flex items-baseline justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Top processes by RSS</h2>
          <span className="text-xs text-muted">refreshed every {REFRESH_MS * 10}ms</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="text-left  px-4 py-2 font-medium">PID</th>
                <th className="text-left  px-4 py-2 font-medium">Name</th>
                <th className="text-right px-4 py-2 font-medium">RSS</th>
                <th className="text-right px-4 py-2 font-medium">CPU %</th>
              </tr>
            </thead>
            <tbody>
              {procs.length === 0 && <tr><td colSpan={4} className="px-4 py-8 text-center text-muted text-sm">Loading…</td></tr>}
              {procs.map((p) => (
                <tr key={p.pid} className="border-b border-border last:border-b-0">
                  <td className="px-4 py-2 num text-xs text-muted">{p.pid}</td>
                  <td className="px-4 py-2 text-xs">{p.name}</td>
                  <td className="px-4 py-2 text-right num">{fmtBytes(p.rss)}</td>
                  <td className="px-4 py-2 text-right num">{p.cpu_percent.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel p-4 text-xs text-muted">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted mb-2 normal-case">Auto-pruning</h2>
        <p>Logs and events are pruned automatically:</p>
        <ul className="list-disc list-inside mt-1 space-y-0.5">
          <li>ClickHouse <code className="text-text">raw_flow_events</code> &amp; <code className="text-text">raw_threat_events</code> — TTL based, edit on Storage Health</li>
          <li>PG <code className="text-text">audit_logs</code> — pruned after 90 days</li>
          <li>PG <code className="text-text">collector_runs</code> — pruned after 14 days</li>
          <li>If disk &gt; 90%, the watchdog triggers an emergency CH compaction + tightens TTLs by 25%</li>
        </ul>
      </div>
    </div>
  );
}
