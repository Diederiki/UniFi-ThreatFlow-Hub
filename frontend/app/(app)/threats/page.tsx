"use client";

import { useEffect, useState } from "react";
import { eventsApi, type EventsPage, type ThreatEvent } from "@/lib/dashboard";
import { useTimeframe } from "@/lib/timeframe";
import { useToast } from "@/components/Toast";
import { AdvancedFilters, type FilterValues } from "@/components/AdvancedFilters";
import { THREAT_FILTERS } from "@/lib/filterDefs";

function severityCls(s: string): string {
  if (s === "critical" || s === "high") return "bg-danger/15 text-danger border-danger/30";
  if (s === "medium") return "bg-warn/15 text-warn border-warn/30";
  return "bg-panel2 text-muted border-border";
}

function MitreChips({ techniques, tactics }: { techniques: string[]; tactics: string[] }) {
  if (techniques.length === 0 && tactics.length === 0) return <span className="text-muted">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {techniques.map((t) => (
        <a
          key={t}
          href={`https://attack.mitre.org/techniques/${t.replace(".", "/")}/`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[10px] px-1.5 py-0.5 rounded border border-accent/30 bg-accent/10 text-accent hover:bg-accent/20"
          title={`MITRE technique ${t}${tactics.length ? ` · ${tactics.join(", ")}` : ""}`}
        >
          {t}
        </a>
      ))}
    </div>
  );
}

function CveRefs({ refs }: { refs: string[] }) {
  if (refs.length === 0) return <span className="text-muted">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {refs.map((c) => (
        <a
          key={c}
          href={`https://nvd.nist.gov/vuln/detail/${c}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[10px] px-1.5 py-0.5 rounded border border-warn/30 bg-warn/10 text-warn hover:bg-warn/20"
          title={`Lookup ${c} on NVD`}
        >
          {c}
        </a>
      ))}
    </div>
  );
}

export default function ThreatsPage() {
  const { timeframe } = useTimeframe();
  const toast = useToast();
  const [data, setData] = useState<EventsPage<ThreatEvent> | null>(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState<FilterValues>({});
  const [page, setPage] = useState(1);

  async function reload() {
    setLoading(true);
    try {
      const apiArgs: Record<string, string> = {};
      for (const [k, v] of Object.entries(filters)) if (v !== undefined && v !== "") apiArgs[k] = String(v);
      const r = await eventsApi.threats(timeframe, { ...apiArgs, page, page_size: 50 });
      setData(r);
    } catch (e) {
      toast.push(e instanceof Error ? e.message : "Load failed", "danger");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { reload(); /* eslint-disable-next-line */ }, [timeframe, page, JSON.stringify(filters)]);
  useEffect(() => { setPage(1); }, [JSON.stringify(filters)]);

  function csvUrl(): string {
    const params = new URLSearchParams({ timeframe });
    for (const [k, v] of Object.entries(filters)) if (v !== undefined && v !== "") params.set(k, String(v));
    return `/api/threats.csv?${params.toString()}`;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold">Threats</h1>
          <p className="text-xs text-muted">~{data?.total_estimate.toLocaleString() ?? "—"} events in last {timeframe} · page {page}</p>
        </div>
        <a href={csvUrl()} className="btn text-xs">Export CSV</a>
      </div>

      <AdvancedFilters defs={THREAT_FILTERS} value={filters} onChange={setFilters} storageKey="threatflow.filters.threats" />

      <div className="panel overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="text-left px-3 py-2 font-medium">When</th>
              <th className="text-left px-3 py-2 font-medium">Branch</th>
              <th className="text-left px-3 py-2 font-medium">Sev</th>
              <th className="text-left px-3 py-2 font-medium">Signature</th>
              <th className="text-left px-3 py-2 font-medium">MITRE</th>
              <th className="text-left px-3 py-2 font-medium">CVE</th>
              <th className="text-left px-3 py-2 font-medium">Source</th>
              <th className="text-left px-3 py-2 font-medium">Destination</th>
              <th className="text-left px-3 py-2 font-medium">Action</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={9} className="px-4 py-8 text-center text-muted text-sm">Loading…</td></tr>}
            {!loading && data?.items.length === 0 && <tr><td colSpan={9} className="px-4 py-8 text-center text-muted text-sm">No matches.</td></tr>}
            {!loading && data?.items.map((t) => (
              <tr key={t.event_id} className="border-b border-border last:border-b-0 hover:bg-panel2/40 align-top">
                <td className="px-3 py-2 text-xs text-muted whitespace-nowrap">{new Date(t.event_time).toLocaleTimeString()}</td>
                <td className="px-3 py-2 num text-xs">{t.branch_code}</td>
                <td className="px-3 py-2"><span className={`text-[10px] px-1.5 py-0.5 rounded border ${severityCls(t.severity)}`}>{t.severity}</span></td>
                <td className="px-3 py-2 text-xs max-w-[20rem]">{t.signature || "—"}</td>
                <td className="px-3 py-2 text-xs"><MitreChips techniques={t.mitre_techniques ?? []} tactics={t.mitre_tactics ?? []} /></td>
                <td className="px-3 py-2 text-xs"><CveRefs refs={t.cve_refs ?? []} /></td>
                <td className="px-3 py-2 num text-xs">{t.source_ip}</td>
                <td className="px-3 py-2 num text-xs">{t.destination_hostname || t.destination_ip}{t.destination_country ? ` · ${t.destination_country}` : ""}</td>
                <td className="px-3 py-2 text-xs">{t.action}</td>
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
