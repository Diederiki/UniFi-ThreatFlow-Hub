"use client";

import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { TIMEFRAMES, useTimeframe } from "@/lib/timeframe";

export function Topbar({ user }: { user?: { email: string; role: string } }) {
  const router = useRouter();
  const { timeframe, setTimeframe } = useTimeframe();

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    router.replace("/login");
  }

  return (
    <header className="h-14 shrink-0 flex items-center justify-between gap-3 px-4 border-b border-border bg-panel/60 backdrop-blur">
      <div className="flex items-center gap-1 overflow-x-auto">
        {TIMEFRAMES.map((t) => {
          const active = t === timeframe;
          return (
            <button
              key={t}
              onClick={() => setTimeframe(t)}
              className={
                "px-2.5 py-1 text-xs rounded-md border transition-colors " +
                (active
                  ? "bg-accent text-bg border-transparent"
                  : "bg-panel2 text-muted border-border hover:text-text")
              }
            >
              {t}
            </button>
          );
        })}
      </div>

      <div className="flex items-center gap-3">
        {user && (
          <span className="hidden sm:block text-xs text-muted">
            {user.email} <span className="text-accent/70">· {user.role}</span>
          </span>
        )}
        <button onClick={logout} className="btn text-xs">Sign out</button>
      </div>
    </header>
  );
}
