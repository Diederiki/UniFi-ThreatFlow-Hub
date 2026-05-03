"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";

const NAV = [
  { href: "/overview",         label: "Overview" },
  { href: "/threats",          label: "Threats" },
  { href: "/blocked",          label: "Blocked Traffic" },
  { href: "/top-visited",      label: "Top Visited" },
  { href: "/branches",         label: "Branches" },
  { href: "/clients",          label: "Clients" },
  { href: "/destinations",     label: "Destinations" },
  { href: "/categories",       label: "Categories" },
  { href: "/suspicion",        label: "Suspicion Score" },
  { href: "/collector-health", label: "Collector Health" },
  { href: "/storage-health",   label: "Storage Health" },
  { href: "/settings",         label: "Settings" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden md:flex md:w-60 lg:w-64 shrink-0 flex-col border-r border-border bg-panel/60 backdrop-blur">
      <div className="px-4 py-5 border-b border-border">
        <div className="text-xs uppercase tracking-widest text-muted">UniFi</div>
        <div className="font-semibold leading-tight">Threatflow Hub</div>
        <div className="text-xs text-muted">for AmSpec</div>
      </div>
      <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
        {NAV.map((item) => {
          const active = pathname === item.href || pathname?.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                "flex items-center px-3 py-2 rounded-md text-sm transition-colors",
                active
                  ? "bg-accent/15 text-accent border border-accent/30"
                  : "text-text/80 hover:text-text hover:bg-panel2",
              )}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
