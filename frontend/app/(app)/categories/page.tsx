"use client";

import { useEffect, useState } from "react";
import { topApi, type Top } from "@/lib/dashboard";
import { TopList } from "@/components/TopList";
import { useTimeframe } from "@/lib/timeframe";

export default function CategoriesPage() {
  const { timeframe } = useTimeframe();
  const [apps, setApps] = useState<Top | null>(null);
  const [cats, setCats] = useState<Top | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([topApi.applications(timeframe, 30), topApi.categories(timeframe, 30)]).then(([a, c]) => {
      if (cancelled) return; setApps(a); setCats(c);
    });
    return () => { cancelled = true; };
  }, [timeframe]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Categories</h1>
        <p className="text-xs text-muted">Last {timeframe}</p>
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <TopList title="Top applications"          data={apps} />
        <TopList title="Top application categories" data={cats} />
      </div>
    </div>
  );
}
