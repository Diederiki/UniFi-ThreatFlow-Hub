"use client";

import { useEffect, useState } from "react";
import { topApi, type Top } from "@/lib/dashboard";
import { TopList } from "@/components/TopList";
import { useTimeframe } from "@/lib/timeframe";

export default function TopVisitedPage() {
  const { timeframe } = useTimeframe();
  const [domains, setDomains] = useState<Top | null>(null);
  const [apps, setApps] = useState<Top | null>(null);
  const [cats, setCats] = useState<Top | null>(null);
  const [destinations, setDestinations] = useState<Top | null>(null);
  const [clients, setClients] = useState<Top | null>(null);
  const [countries, setCountries] = useState<Top | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function reload() {
      const [d, a, c, dst, cl, co] = await Promise.all([
        topApi.domains(timeframe), topApi.applications(timeframe), topApi.categories(timeframe),
        topApi.destinations(timeframe), topApi.clients(timeframe), topApi.countries(timeframe),
      ]);
      if (cancelled) return;
      setDomains(d); setApps(a); setCats(c); setDestinations(dst); setClients(cl); setCountries(co);
    }
    reload();
    const id = setInterval(reload, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [timeframe]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Top Visited</h1>
        <p className="text-xs text-muted">Last {timeframe} · ranked by event count</p>
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <TopList title="Top domains"      data={domains} />
        <TopList title="Top applications" data={apps} />
        <TopList title="Top categories"   data={cats} />
        <TopList title="Top destinations" data={destinations} />
        <TopList title="Top clients"      data={clients} />
        <TopList title="Top countries"    data={countries} />
      </div>
    </div>
  );
}
