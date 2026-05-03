"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { branchesApi, type Branch } from "@/lib/branches";
import { useToast } from "@/components/Toast";
import { api, ApiError } from "@/lib/api";
import { AdvancedFilters, type FilterValues } from "@/components/AdvancedFilters";
import { BRANCH_FILTERS } from "@/lib/filterDefs";

function statusBadge(b: Branch): { label: string; cls: string } {
  if (!b.enabled) return { label: "disabled", cls: "bg-panel2 text-muted border-border" };
  const s = b.status?.status ?? "unknown";
  if (s === "ok" || s === "running") return { label: s, cls: "bg-success/15 text-success border-success/30" };
  if (s === "error") return { label: s, cls: "bg-danger/15 text-danger border-danger/30" };
  if (s === "never_run") return { label: "never run", cls: "bg-warn/15 text-warn border-warn/30" };
  return { label: s, cls: "bg-panel2 text-muted border-border" };
}

export default function BranchesPage() {
  const toast = useToast();
  const [items, setItems] = useState<Branch[] | null>(null);
  const [filters, setFilters] = useState<FilterValues>({});
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    try {
      const params = new URLSearchParams();
      for (const [k, v] of Object.entries(filters)) if (v !== undefined && v !== "") params.set(k, String(v));
      const qs = params.toString();
      const r = await api<{ items: Branch[]; total: number }>(`/branches${qs ? `?${qs}` : ""}`);
      setItems(r.items);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load branches";
      setError(msg);
    }
  }

  useEffect(() => { reload(); /* eslint-disable-next-line */ }, [JSON.stringify(filters)]);

  async function onToggle(b: Branch) {
    try {
      const updated = b.enabled ? await branchesApi.disable(b.id) : await branchesApi.enable(b.id);
      setItems((arr) => arr?.map((x) => (x.id === b.id ? updated : x)) ?? arr);
      toast.push(`Branch ${updated.enabled ? "enabled" : "disabled"}`, "success");
    } catch (e) {
      toast.push(e instanceof Error ? e.message : "Toggle failed", "danger");
    }
  }

  async function onTest(b: Branch) {
    try {
      const r = await branchesApi.test(b.id);
      if (r.ok) toast.push(`OK · ${r.endpoint_used}${r.is_mock ? " (mock)" : ""}`, "success");
      else toast.push(`Test failed: ${r.error ?? "unknown"}`, "danger");
    } catch (e) {
      toast.push(e instanceof Error ? e.message : "Test failed", "danger");
    }
  }

  async function onDelete(b: Branch) {
    if (!confirm(`Delete branch "${b.name}"? This cannot be undone.`)) return;
    try {
      await branchesApi.delete(b.id);
      setItems((arr) => arr?.filter((x) => x.id !== b.id) ?? arr);
      toast.push("Branch deleted", "success");
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 403 ? "Only admins can delete branches" : (e instanceof Error ? e.message : "Delete failed");
      toast.push(msg, "danger");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Branches</h1>
          <p className="text-xs text-muted">{items === null ? "Loading…" : `${items.length} configured`}</p>
        </div>
        <Link href="/branches/new" className="btn btn-primary">+ Add branch</Link>
      </div>

      <AdvancedFilters defs={BRANCH_FILTERS} value={filters} onChange={setFilters} storageKey="threatflow.filters.branches" />

      {error && (
        <div className="panel p-4 text-sm text-danger border-danger/30">{error}</div>
      )}

      {items !== null && items.length === 0 && (
        <div className="panel p-8 text-center text-muted text-sm">
          No branches yet. Click <span className="text-text">Add branch</span> to onboard your first UniFi gateway.
        </div>
      )}

      {items !== null && items.length > 0 && (
        <div className="panel overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Branch</th>
                <th className="text-left px-4 py-2 font-medium">Code</th>
                <th className="text-left px-4 py-2 font-medium">Location</th>
                <th className="text-left px-4 py-2 font-medium">Controller</th>
                <th className="text-left px-4 py-2 font-medium">Status</th>
                <th className="text-right px-4 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((b) => {
                const badge = statusBadge(b);
                return (
                  <tr key={b.id} className="border-b border-border last:border-b-0 hover:bg-panel2/40">
                    <td className="px-4 py-3">
                      <Link href={`/branches/${b.id}`} className="font-medium text-text hover:text-accent">
                        {b.name}
                      </Link>
                      {b.tags?.length > 0 && (
                        <div className="mt-1 flex gap-1 flex-wrap">
                          {b.tags.map((t) => (
                            <span key={t} className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-panel2 text-muted border border-border">
                              {t}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 num text-muted">{b.branch_code}</td>
                    <td className="px-4 py-3 text-muted">{[b.city, b.country].filter(Boolean).join(", ") || "—"}</td>
                    <td className="px-4 py-3 num text-muted text-xs truncate max-w-[18rem]">{b.controller_url}</td>
                    <td className="px-4 py-3">
                      <span className={`text-[11px] px-2 py-0.5 rounded-md border ${badge.cls}`}>{badge.label}</span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1.5">
                        <button onClick={() => onTest(b)} className="btn text-xs">Test</button>
                        <button onClick={() => onToggle(b)} className="btn text-xs">{b.enabled ? "Disable" : "Enable"}</button>
                        <Link href={`/branches/${b.id}`} className="btn text-xs">Edit</Link>
                        <button onClick={() => onDelete(b)} className="btn text-xs hover:text-danger">Delete</button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
