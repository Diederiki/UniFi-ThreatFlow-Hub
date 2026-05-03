"use client";

import { createContext, useContext, useEffect, useState } from "react";

export const TIMEFRAMES = [
  "5m", "15m", "1h", "4h", "12h", "24h",
  "3d", "7d", "14d", "1m", "6m", "1y",
] as const;
export type Timeframe = typeof TIMEFRAMES[number];

type Ctx = { timeframe: Timeframe; setTimeframe: (t: Timeframe) => void };
const TimeframeCtx = createContext<Ctx | null>(null);

const STORAGE_KEY = "threatflow.timeframe";

export function TimeframeProvider({ children }: { children: React.ReactNode }) {
  const [timeframe, setTimeframe] = useState<Timeframe>("24h");

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY) as Timeframe | null;
      if (saved && (TIMEFRAMES as readonly string[]).includes(saved)) setTimeframe(saved);
    } catch {}
  }, []);

  function setAndPersist(t: Timeframe) {
    setTimeframe(t);
    try { window.localStorage.setItem(STORAGE_KEY, t); } catch {}
  }

  return <TimeframeCtx.Provider value={{ timeframe, setTimeframe: setAndPersist }}>{children}</TimeframeCtx.Provider>;
}

export function useTimeframe(): Ctx {
  const ctx = useContext(TimeframeCtx);
  if (!ctx) throw new Error("useTimeframe must be inside TimeframeProvider");
  return ctx;
}
