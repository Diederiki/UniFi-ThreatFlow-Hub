"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";

export type FilterType = "text" | "contains" | "select" | "number-min" | "boolean";

export type FilterDef = {
  /** URL/api param name (e.g. "branch_id"). */
  key: string;
  /** Human label */
  label: string;
  type: FilterType;
  placeholder?: string;
  /** For select: enum options */
  options?: { value: string; label: string }[];
  /** For select: async loader (fired once on mount) */
  loadOptions?: () => Promise<{ value: string; label: string }[]>;
};

export type FilterValues = Record<string, string | number | boolean | undefined>;

function pillLabel(def: FilterDef, raw: string | number | boolean | undefined, options: { value: string; label: string }[]): string {
  if (raw === undefined || raw === "" || raw === false) return "";
  if (def.type === "select") {
    const opt = options.find((o) => o.value === String(raw));
    return `${def.label}: ${opt?.label ?? raw}`;
  }
  if (def.type === "boolean") return def.label;
  if (def.type === "number-min") return `${def.label} ≥ ${raw}`;
  return `${def.label}: ${raw}`;
}

export function AdvancedFilters({
  defs,
  value,
  onChange,
  storageKey,
}: {
  defs: FilterDef[];
  value: FilterValues;
  onChange: (next: FilterValues) => void;
  /** Persists active filter set to localStorage so the page remembers them */
  storageKey?: string;
}) {
  const [open, setOpen] = useState(false);
  const [opts, setOpts] = useState<Record<string, { value: string; label: string }[]>>({});
  const drawerRef = useRef<HTMLDivElement>(null);

  // Load async options once on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const map: Record<string, { value: string; label: string }[]> = {};
      for (const d of defs) {
        if (d.options) map[d.key] = d.options;
        else if (d.loadOptions) {
          try { map[d.key] = await d.loadOptions(); } catch { map[d.key] = []; }
        }
      }
      if (!cancelled) setOpts(map);
    })();
    return () => { cancelled = true; };
  }, [defs]);

  // Restore from localStorage on mount
  useEffect(() => {
    if (!storageKey) return;
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object") onChange(parsed);
      }
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  // Persist on every change
  useEffect(() => {
    if (!storageKey) return;
    try { window.localStorage.setItem(storageKey, JSON.stringify(value)); } catch {}
  }, [value, storageKey]);

  // Click outside to close
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (drawerRef.current && !drawerRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const active = useMemo(
    () => defs.filter((d) => {
      const v = value[d.key];
      return v !== undefined && v !== "" && v !== false && v !== 0;
    }),
    [defs, value]
  );

  function setField(key: string, v: string | number | boolean | undefined) {
    const next = { ...value };
    if (v === undefined || v === "" || v === false || v === 0) delete next[key];
    else next[key] = v;
    onChange(next);
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setOpen((o) => !o)}
          className={clsx(
            "btn text-xs flex items-center gap-1.5",
            active.length > 0 && "border-accent/40 text-accent",
          )}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 4h18l-7 9v6l-4-2v-4z"/></svg>
          Filters
          {active.length > 0 && <span className="num bg-accent text-bg rounded-full px-1.5 py-0.5 text-[10px] leading-none">{active.length}</span>}
        </button>

        {active.map((d) => (
          <button
            key={d.key}
            onClick={() => setField(d.key, undefined)}
            className="text-xs px-2 py-1 rounded-md border border-accent/30 bg-accent/10 text-accent flex items-center gap-1 hover:bg-accent/20"
            title="Click to remove"
          >
            <span>{pillLabel(d, value[d.key], opts[d.key] ?? [])}</span>
            <span className="text-accent/70">×</span>
          </button>
        ))}

        {active.length > 0 && (
          <button onClick={() => onChange({})} className="text-xs text-muted hover:text-danger ml-1">Clear all</button>
        )}
      </div>

      {open && (
        <div ref={drawerRef} className="panel p-4 grid sm:grid-cols-2 lg:grid-cols-3 gap-3 shadow-glow">
          {defs.map((d) => {
            const v = value[d.key];
            const options = opts[d.key] ?? [];
            return (
              <div key={d.key} className="space-y-1">
                <label className="block text-xs uppercase tracking-wide text-muted">{d.label}</label>
                {d.type === "text" || d.type === "contains" ? (
                  <input
                    type="text"
                    className="input text-sm"
                    value={(v as string) ?? ""}
                    placeholder={d.placeholder ?? (d.type === "contains" ? "contains…" : "exact match")}
                    onChange={(e) => setField(d.key, e.target.value)}
                  />
                ) : d.type === "select" ? (
                  <select
                    className="input text-sm"
                    value={(v as string) ?? ""}
                    onChange={(e) => setField(d.key, e.target.value)}
                  >
                    <option value="">— any —</option>
                    {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                ) : d.type === "number-min" ? (
                  <input
                    type="number"
                    min={0}
                    className="input text-sm"
                    value={(v as number) ?? ""}
                    placeholder={d.placeholder ?? "0"}
                    onChange={(e) => setField(d.key, e.target.value === "" ? undefined : Number(e.target.value))}
                  />
                ) : d.type === "boolean" ? (
                  <select
                    className="input text-sm"
                    value={v === true ? "true" : v === false ? "false" : ""}
                    onChange={(e) => {
                      if (e.target.value === "true") setField(d.key, true);
                      else if (e.target.value === "false") setField(d.key, false);
                      else setField(d.key, undefined);
                    }}
                  >
                    <option value="">— any —</option>
                    <option value="true">yes</option>
                    <option value="false">no</option>
                  </select>
                ) : null}
              </div>
            );
          })}
          <div className="sm:col-span-2 lg:col-span-3 flex justify-end pt-2 gap-2">
            <button onClick={() => onChange({})} className="btn text-xs">Clear all</button>
            <button onClick={() => setOpen(false)} className="btn btn-primary text-xs">Done</button>
          </div>
        </div>
      )}
    </div>
  );
}
