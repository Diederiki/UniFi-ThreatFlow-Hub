"use client";

import { useEffect, useState } from "react";
import { topApi, type Top } from "@/lib/dashboard";
import { TopList } from "@/components/TopList";
import { useTimeframe } from "@/lib/timeframe";

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
        <p className="text-xs text-muted">Last {timeframe}</p>
      </div>
      <div className="grid lg:grid-cols-3 gap-4">
        <TopList title="Top destination IPs" data={destinations} />
        <TopList title="Top domains"         data={domains} />
        <TopList title="Top countries"       data={countries} />
      </div>
    </div>
  );
}
