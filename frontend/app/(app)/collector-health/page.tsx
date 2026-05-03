"use client";

import { useEffect, useState } from "react";
import { collectorsApi, type CollectorBranchStatus, type CollectorRun } from "@/lib/collectors";
import { useToast } from "@/components/Toast";

function fmtRel(iso: string | null): string {
  if (!iso) return "—";
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 1000) return "just now";
  if (ms < 60_000) return `${Math.round(ms / 1000)}s ago`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m ago`;
  if (ms < 86_400_000) return `${Math.round(ms / 3_600_000)}h ago`;
  return new Date(iso).toLocaleString();
}

function statusPill(status: string, enabled: boolean) {
  if (!enabled) return { label: "disabled", cls: "bg-panel2 text-muted border-border" };
  if (status === "ok") return { label: "ok", cls: "bg-success/15 text-success border-success/30" };
  if (status === "running") return { label: "running", cls: "bg-accent/15 text-accent border-accent/30" };
  if (status === "error") return { label: "error", cls: "bg-danger/15 text-danger border-danger/30" };
  if (status === "never_run") return { label: "never run", cls: "bg-warn/15 text-warn border-warn/30" };
  return { label: status, cls: "bg-panel2 text-muted border-border" };
}

export default function CollectorHealthPage() {
  const toast = useToast();
  const [items, setItems] = useState<CollectorBranchStatus[] | null>(null);
  const [runs, setRuns] = useState<CollectorRun[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    try {
      const [s, r] = await Promise.all([
        collectorsApi.status(),
        collectorsApi.runs(undefined, 30),
      ]);
      setItems(s.items);
      setRuns(r.items);
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

  async function trigger(b: CollectorBranchStatus) {
    try {
      await collectorsApi.runBranch(b.branch_id);
      toast.push(`Queued for ${b.branch_code}`, "success");
    } catch (e) {
      toast.push(e instanceof Error ? e.message : "Queue failed", "danger");
    }
  }

  if (error) return <div className="panel p-4 text-sm text-danger border-danger/30">{error}</div>;
  if (!items) return <div className="text-sm text-muted">Loading…</div>;

  const okCount = items.filter((i) => i.status === "ok" && i.enabled).length;
  const errCount = items.filter((i) => i.status === "error" && i.enabled).length;
  const disabled = items.filter((i) => !i.enabled).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">Collector Health</h1>
        <p className="text-xs text-muted">{items.length} branch(es) · {okCount} ok · {errCount} error · {disabled} disabled</p>
      </div>

      {items.length === 0 ? (
        <div className="panel p-8 text-center text-muted text-sm">
          No branches configured. Add one under <span className="text-text">Branches</span>.
        </div>
      ) : (
        <div className="panel overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Branch</th>
                <th className="text-left px-4 py-2 font-medium">Status</th>
                <th className="text-left px-4 py-2 font-medium">Last success</th>
                <th className="text-right px-4 py-2 font-medium">Events</th>
                <th className="text-right px-4 py-2 font-medium">Duration</th>
                <th className="text-left px-4 py-2 font-medium">Endpoint</th>
                <th className="text-left px-4 py-2 font-medium">UniFi OS</th>
                <th className="text-right px-4 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((b) => {
                const p = statusPill(b.status, b.enabled);
                return (
                  <tr key={b.branch_id} className="border-b border-border last:border-b-0 hover:bg-panel2/40">
                    <td className="px-4 py-3">
                      <div className="font-medium">{b.branch_name}</div>
                      <div className="text-xs text-muted num">{b.branch_code}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-[11px] px-2 py-0.5 rounded-md border ${p.cls}`}>{p.label}</span>
                      {b.last_error && (
                        <div className="mt-1 text-[10px] text-danger truncate max-w-[14rem]">{b.last_error}</div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-muted">{fmtRel(b.last_success_at)}</td>
                    <td className="px-4 py-3 text-right num">{b.last_event_count ?? "—"}</td>
                    <td className="px-4 py-3 text-right num text-muted">{b.last_duration_ms !== null ? `${b.last_duration_ms} ms` : "—"}</td>
                    <td className="px-4 py-3 text-xs text-muted truncate max-w-[20rem] num">{b.last_endpoint_used ?? "—"}</td>
                    <td className="px-4 py-3 text-xs text-muted">{b.unifi_os_version ?? "—"}</td>
                    <td className="px-4 py-3 text-right">
                      <button onClick={() => trigger(b)} className="btn text-xs">Run now</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="panel">
        <div className="px-4 py-3 border-b border-border">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">Recent runs (latest 30)</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Started</th>
                <th className="text-left px-4 py-2 font-medium">Branch</th>
                <th className="text-left px-4 py-2 font-medium">Status</th>
                <th className="text-right px-4 py-2 font-medium">Events</th>
                <th className="text-right px-4 py-2 font-medium">Duration</th>
                <th className="text-left px-4 py-2 font-medium">Error</th>
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-muted text-sm">No runs yet — collector ticks every 30s.</td></tr>
              )}
              {runs.map((r) => {
                const code = items.find((i) => i.branch_id === r.branch_id)?.branch_code ?? "—";
                const ok = r.status === "ok";
                return (
                  <tr key={r.id} className="border-b border-border last:border-b-0">
                    <td className="px-4 py-2 text-xs text-muted">{fmtRel(r.started_at)}</td>
                    <td className="px-4 py-2 num text-xs">{code}</td>
                    <td className="px-4 py-2">
                      <span className={`text-[11px] px-2 py-0.5 rounded-md border ${ok ? "bg-success/15 text-success border-success/30" : "bg-danger/15 text-danger border-danger/30"}`}>
                        {r.status}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right num">{r.event_count ?? "—"}</td>
                    <td className="px-4 py-2 text-right num text-muted">{r.duration_ms !== null ? `${r.duration_ms} ms` : "—"}</td>
                    <td className="px-4 py-2 text-xs text-muted truncate max-w-[28rem]">{r.error_message ?? ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
