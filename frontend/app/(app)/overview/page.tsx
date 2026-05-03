export default function OverviewPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">Overview</h1>
        <p className="text-sm text-muted">
          Phase 1 placeholder. Real KPI tiles, traffic trend, threat trend, branch heatmap and
          top-suspicious widgets ship in Phase 5.
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Total branches",    value: "—" },
          { label: "Online collectors", value: "—" },
          { label: "Flows (timeframe)", value: "—" },
          { label: "Blocked",           value: "—" },
          { label: "Allowed",           value: "—" },
          { label: "IDS / IPS events",  value: "—" },
          { label: "High-risk events",  value: "—" },
          { label: "Top sus. branch",   value: "—" },
        ].map((k) => (
          <div key={k.label} className="panel p-4">
            <div className="text-xs text-muted uppercase tracking-wide">{k.label}</div>
            <div className="mt-2 text-2xl num">{k.value}</div>
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="panel p-4 h-64 flex items-center justify-center text-muted text-sm">
          Traffic volume trend (Phase 5)
        </div>
        <div className="panel p-4 h-64 flex items-center justify-center text-muted text-sm">
          Threat trend (Phase 5)
        </div>
      </div>
    </div>
  );
}
