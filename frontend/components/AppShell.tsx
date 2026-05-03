"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { Sidebar } from "./Sidebar";
import { Topbar, type Timeframe } from "./Topbar";

type Me = { email: string; role: string; name: string | null };

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<Me | null>(null);
  const [timeframe, setTimeframe] = useState<Timeframe>("24h");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api<Me>("/auth/me")
      .then((u) => { if (!cancelled) { setUser(u); setLoading(false); } })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          router.replace("/login");
        } else {
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [router]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted text-sm">
        Loading…
      </div>
    );
  }

  return (
    <div className="min-h-screen flex">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Topbar
          user={user ? { email: user.email, role: user.role } : undefined}
          timeframe={timeframe}
          onTimeframeChange={setTimeframe}
        />
        <main className="flex-1 p-4 lg:p-6 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
