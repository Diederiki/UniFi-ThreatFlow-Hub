"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { topApi, type Top } from "@/lib/dashboard";
import { TopList } from "@/components/TopList";
import { useTimeframe } from "@/lib/timeframe";

function ClickableTopList({ title, data, hrefBase }: { title: string; data: Top | null; hrefBase: string }) {
  if (!data) return <TopList title={title} data={data} />;
  const max = Math.max(1, ...data.items.map((i) => i.value));
  return (
    <div className="panel p-4">
      <div className="flex items-baseline justify-between mb-3">
        <div className="text-xs text-muted uppercase">{title}</div>
        <div className="text-xs text-muted">{data.items.length}</div>
      </div>
      <ul className="space-y-1.5">
        {data.items.map((it, i) => (
          <li key={`${it.label}-${i}`} className="text-sm">
            <Link href={`${hrefBase}/${encodeURIComponent(it.label)}`} className="hover:text-accent">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate">{it.label || "—"}</span>
                <span className="num text-muted">{it.value.toLocaleString()}</span>
              </div>
            </Link>
            <div className="h-1 mt-1 bg-panel2 rounded overflow-hidden">
              <div className="h-full bg-accent/40" style={{ width: `${(it.value / max) * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function DestinationsPage() {
  const { timeframe } = useTimeframe();
  const [destinations, setDest] = useState<Top | null>(null);
  const [domains, setDomains] = useState<Top | null>(null);
  const [countries, setCountries] = useState<Top | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      topApi.destinations(timeframe, 30),
      topApi.domains(timeframe, 30),
      topApi.countries(timeframe, 20),
    ]).then(([dst, dom, co]) => { if (cancelled) return; setDest(dst); setDomains(dom); setCountries(co); });
    return () => { cancelled = true; };
  }, [timeframe]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Destinations</h1>
        <p className="text-xs text-muted">Last {timeframe} · click an IP to drill down</p>
      </div>
      <div className="grid lg:grid-cols-3 gap-4">
        <ClickableTopList title="Top destination IPs" data={destinations} hrefBase="/destinations" />
        <TopList title="Top domains"   data={domains} />
        <TopList title="Top countries" data={countries} />
      </div>
    </div>
  );
}
