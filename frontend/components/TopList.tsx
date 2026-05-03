"use client";

import type { Top } from "@/lib/dashboard";

export function TopList({ title, data, valueLabel = "events" }: { title: string; data: Top | null; valueLabel?: string }) {
  if (!data) return <div className="panel p-4 h-full"><div className="text-xs text-muted uppercase">{title}</div><div className="text-muted text-xs mt-3">Loading…</div></div>;
  const max = Math.max(1, ...data.items.map((i) => i.value));
  return (
    <div className="panel p-4">
      <div className="flex items-baseline justify-between mb-3">
        <div className="text-xs text-muted uppercase">{title}</div>
        <div className="text-xs text-muted">{data.items.length} · {valueLabel}</div>
      </div>
      {data.items.length === 0 ? (
        <div className="text-muted text-xs">No data</div>
      ) : (
        <ul className="space-y-1.5">
          {data.items.map((it, i) => (
            <li key={`${it.label}-${i}`} className="text-sm">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate">{it.label || "—"}</span>
                <span className="num text-muted">{it.value.toLocaleString()}</span>
              </div>
              <div className="h-1 mt-1 bg-panel2 rounded overflow-hidden">
                <div className="h-full bg-accent/40" style={{ width: `${(it.value / max) * 100}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
