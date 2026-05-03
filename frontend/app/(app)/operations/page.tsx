"use client";

import { useEffect, useRef, useState } from "react";
import { observabilityApi, type HostMetrics, type ProcessRow } from "@/lib/observability";
import { operationsApi, type PruneReport, type ReclaimEstimate } from "@/lib/operations";
import { Ring } from "@/components/charts/Ring";
import { useToast } from "@/components/Toast";
import { ApiError } from "@/lib/api";

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
function fmtRel(iso: string | null): string {
  if (!iso) return "—";
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return `${Math.round(ms / 1000)}s ago`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m ago`;
  return new Date(iso).toLocaleString();
}

const REFRESH_MS = 2000;

export default function OperationsPage() {
  const toast = useToast();
  const [host, setHost] = useState<HostMetrics | null>(null);
  const [procs, setProcs] = useState<ProcessRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastPrune, setLastPrune] = useState<PruneReport | null>(null);
  const [estimate, setEstimate] = useState<ReclaimEstimate | null>(null);
  const [pruning, setPruning] = useState(false);
  const procTickRef = useRef(0);

  async function reloadOps() {
    try {
      const [lp, est] = await Promise.all([
        operationsApi.lastPrune(),
        operationsApi.reclaimEstimate(),
      ]);
      setLastPrune(lp);
      setEstimate(est);
    } catch {
      // non-fatal
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const h = await observabilityApi.host();
        if (cancelled) return;
        setHost(h);
        setError(null);
        if (procTickRef.current % 10 === 0) {
          const p = await observabilityApi.processes(15);
          if (!cancelled) setProcs(p.items);
        }
        if (procTickRef.current % 30 === 0) {
          await reloadOps();
        }
        procTickRef.current += 1;
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Load failed");
      }
    }
    tick();
    reloadOps();
    const id = setInterval(tick, REFRESH_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  async function runPrune() {
    setPruning(true);
    try {
      const r = await operationsApi.runPrune();
      setLastPrune(r);
      const watch = r.watchdog_fired ? ` · WATCHDOG FIRED (${r.actions_taken.join(", ") || "no actions"})` : "";
      toast.push(`Pruned ${r.audit_logs_deleted + r.collector_runs_deleted} rows · disk ${r.disk_percent.toFixed(1)}%${watch}`, "success");
      await reloadOps();
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 403 ? "Only admins can run prune" : (e instanceof Error ? e.message : "Prune failed");
      toast.push(msg, "danger");
    } finally {
      setPruning(false);
    }
  }

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
            <div className="flex items-center justify-between text-xs uppercase text-muted mb-3"><span>CPU</span><span className="text-muted/60">⚙</span></div>
            <Ring percent={host?.cpu.percent ?? 0} label={`${(host?.cpu.percent ?? 0).toFixed(0)}%`} sublabel={host ? `${host.cpu.cores} cores` : "—"} color="#22d3ee" />
          </div>
          <div className="panel p-5">
            <div className="flex items-center justify-between text-xs uppercase text-muted mb-3"><span>Memory</span><span className="text-muted/60">▭</span></div>
            <Ring percent={host?.memory.percent ?? 0} label={`${(host?.memory.percent ?? 0).toFixed(0)}%`} sublabel={host ? `${fmtBytes(host.memory.used)} / ${fmtBytes(host.memory.total)}` : "—"} color="#7c3aed" />
          </div>
          <div className="panel p-5">
            <div className="flex items-center justify-between text-xs uppercase text-muted mb-3"><span>Disk</span><span className="text-muted/60">⌘</span></div>
            <Ring percent={host?.disk.percent ?? 0} label={`${(host?.disk.percent ?? 0).toFixed(0)}%`} sublabel={host ? `${fmtBytes(host.disk.used)} / ${fmtBytes(host.disk.total)}` : "—"} color={(host?.disk.percent ?? 0) > 85 ? "#ef4444" : (host?.disk.percent ?? 0) > 70 ? "#f59e0b" : "#22c55e"} />
          </div>
          <div className="panel p-5">
            <div className="flex items-center justify-between text-xs uppercase text-muted mb-3"><span>Network</span><span className="text-muted/60">↕</span></div>
            <Ring percent={Math.min(100, ((host?.network.rx_bytes_per_s ?? 0) + (host?.network.tx_bytes_per_s ?? 0)) / (1024 * 1024) * 10)} label={fmtRate((host?.network.rx_bytes_per_s ?? 0) + (host?.network.tx_bytes_per_s ?? 0))} sublabel={host ? `↓ ${fmtRate(host.network.rx_bytes_per_s)} · ↑ ${fmtRate(host.network.tx_bytes_per_s)}` : "—"} color="#22d3ee" />
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="panel p-5">
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Auto-pruner</h2>
            <button onClick={runPrune} disabled={pruning} className="btn btn-primary text-xs disabled:opacity-50">
              {pruning ? "Running…" : "Run prune now"}
            </button>
          </div>

          {!lastPrune ? (
            <div className="text-sm text-muted">No prune run yet. The auto-pruner kicks in 60s after backend boot, then every hour.</div>
          ) : (
            <div className="space-y-3">
              <div className="text-xs text-muted">last run {fmtRel(lastPrune.finished_at)}</div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="bg-panel2 rounded p-2">
                  <div className="text-[10px] uppercase text-muted">audit logs deleted</div>
                  <div className="num text-lg">{lastPrune.audit_logs_deleted.toLocaleString()}</div>
                </div>
                <div className="bg-panel2 rounded p-2">
                  <div className="text-[10px] uppercase text-muted">collector runs deleted</div>
                  <div className="num text-lg">{lastPrune.collector_runs_deleted.toLocaleString()}</div>
                </div>
                <div className="bg-panel2 rounded p-2">
                  <div className="text-[10px] uppercase text-muted">CH rollups optimized</div>
                  <div className="num text-lg">{lastPrune.rollups_optimized.length}</div>
                </div>
                <div className={`rounded p-2 ${lastPrune.watchdog_fired ? "bg-danger/10 border border-danger/30" : "bg-panel2"}`}>
                  <div className="text-[10px] uppercase text-muted">disk watchdog</div>
                  <div className={`num text-lg ${lastPrune.watchdog_fired ? "text-danger" : ""}`}>{lastPrune.watchdog_fired ? "FIRED" : "ok"}</div>
                </div>
              </div>
              {lastPrune.actions_taken.length > 0 && (
                <div className="text-xs">
                  <div className="text-muted mb-1">Watchdog actions:</div>
                  <ul className="list-disc list-inside text-warn">{lastPrune.actions_taken.map((a, i) => <li key={i}>{a}</li>)}</ul>
                </div>
              )}
              {lastPrune.errors.length > 0 && (
                <div className="text-xs text-danger">{lastPrune.errors.join(" · ")}</div>
              )}
            </div>
          )}
        </div>

        <div className="panel p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted mb-3">Reclaim now</h2>
          {!estimate ? (
            <div className="text-sm text-muted">Loading estimate…</div>
          ) : (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span>Audit-log rows ready to prune</span><span className="num">{estimate.audit_logs_rows_to_delete.toLocaleString()}</span></div>
              <div className="flex justify-between"><span>Collector-run rows ready to prune</span><span className="num">{estimate.collector_runs_rows_to_delete.toLocaleString()}</span></div>
              <div className="flex justify-between"><span>CH failed-insert rows</span><span className="num">{estimate.failed_inserts_rows.toLocaleString()}</span></div>
              <div className="border-t border-border pt-2 mt-2 text-xs text-muted">{estimate.docker_hint}</div>
            </div>
          )}
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
    </div>
  );
}
