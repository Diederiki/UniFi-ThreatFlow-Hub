"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Trend } from "@/lib/dashboard";

const COLORS: Record<string, string> = {
  allowed: "#22d3ee",
  blocked: "#ef4444",
  ids_ips: "#7c3aed",
  high_risk: "#f43f5e",
  medium_risk: "#f59e0b",
  low_risk: "#22c55e",
};

export function TrendArea({ trend, height = 220 }: { trend: Trend | null; height?: number }) {
  if (!trend) return <div className="h-full flex items-center justify-center text-muted text-xs">—</div>;
  if (trend.series.length === 0 || trend.series.every((s) => s.points.length === 0))
    return <div className="h-full flex items-center justify-center text-muted text-xs">No data in this window</div>;

  // merge series into a single rows array indexed by t
  const map = new Map<string, Record<string, number | string>>();
  for (const s of trend.series) {
    for (const p of s.points) {
      const key = p.t;
      const row = map.get(key) ?? { t: key };
      row[s.name] = p.value;
      map.set(key, row);
    }
  }
  const rows = [...map.values()].sort((a, b) => String(a.t).localeCompare(String(b.t)));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={rows} margin={{ top: 5, right: 8, left: 0, bottom: 0 }}>
        <defs>
          {trend.series.map((s) => (
            <linearGradient key={s.name} id={`grad-${s.name}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={COLORS[s.name] ?? "#7c8aa6"} stopOpacity={0.55} />
              <stop offset="100%" stopColor={COLORS[s.name] ?? "#7c8aa6"} stopOpacity={0.05} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid stroke="#1f2a44" strokeDasharray="2 4" />
        <XAxis dataKey="t" tick={{ fill: "#7c8aa6", fontSize: 10 }} tickFormatter={(v) => new Date(v).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} minTickGap={32} />
        <YAxis tick={{ fill: "#7c8aa6", fontSize: 10 }} width={42} />
        <Tooltip
          contentStyle={{ backgroundColor: "#161d2f", border: "1px solid #1f2a44", borderRadius: 6, fontSize: 12 }}
          labelStyle={{ color: "#dde4f1" }}
          labelFormatter={(v) => new Date(v as string).toLocaleString()}
        />
        {trend.series.map((s) => (
          <Area
            key={s.name}
            type="monotone"
            dataKey={s.name}
            stroke={COLORS[s.name] ?? "#7c8aa6"}
            strokeWidth={1.5}
            fill={`url(#grad-${s.name})`}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
