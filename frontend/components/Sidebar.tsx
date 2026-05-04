"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";

type NavItem = { href: string; label: string; section: string };

const NAV: NavItem[] = [
  { section: "Monitor",    href: "/overview",         label: "Overview" },
  { section: "Monitor",    href: "/threats",          label: "Threats" },
  { section: "Monitor",    href: "/blocked",          label: "Blocked Traffic" },
  { section: "Monitor",    href: "/top-visited",      label: "Top Visited" },
  { section: "Detect",     href: "/suspicion",        label: "Suspicion Score" },
  { section: "Inventory",  href: "/branches",         label: "Branches" },
  { section: "Inventory",  href: "/clients",          label: "Clients" },
  { section: "Inventory",  href: "/destinations",     label: "Destinations" },
  { section: "Inventory",  href: "/categories",       label: "Categories" },
  { section: "Operations", href: "/operations",       label: "Observability" },
  { section: "Operations", href: "/ipfix-sources",    label: "IPFIX Sources" },
  { section: "Operations", href: "/collector-health", label: "Collector Health" },
  { section: "Operations", href: "/storage-health",   label: "Storage Health" },
  { section: "Admin",      href: "/settings",         label: "Settings" },
];

export function Sidebar() {
  const pathname = usePathname();
  let lastSection: string | undefined;
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
          const showHeader = item.section !== lastSection;
          lastSection = item.section;
          return (
            <div key={item.href}>
              {showHeader && (
                <div className="px-3 pt-3 pb-1 text-[10px] uppercase tracking-widest text-muted/70">{item.section}</div>
              )}
              <Link
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
            </div>
          );
        })}
      </nav>
    </aside>
  );
}
