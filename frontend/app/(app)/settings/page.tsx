"use client";

import { useEffect, useState } from "react";
import { suspicionApi, type ScoringWeights } from "@/lib/suspicion";
import { Field, TextInput } from "@/components/forms/Field";
import { useToast } from "@/components/Toast";
import { api, ApiError } from "@/lib/api";
import { ProfilePanel } from "@/components/settings/ProfilePanel";
import { UsersPanel } from "@/components/settings/UsersPanel";
import { SsoPanel } from "@/components/settings/SsoPanel";
import { meApi, type AppUser } from "@/lib/users";

const SCORING_LABEL: Record<keyof ScoringWeights, string> = {
  high_risk_event: "High-risk IDS/IPS event",
  medium_risk_event: "Medium-risk IDS/IPS event",
  low_risk_event: "Low-risk event",
  blocked_event: "Blocked intrusion event",
  repeated_client: "Repeated same-client detection",
  outbound_suspicious: "Outbound suspicious destination",
  malware_botnet: "Malware / botnet signature",
  large_transfer: "Large unusual data transfer",
  known_false_positive: "Known false positive (negative)",
};
const SCORING_KEYS = Object.keys(SCORING_LABEL) as (keyof ScoringWeights)[];

type GeneralSettings = {
  collector_max_concurrent: number;
  polling_interval_seconds_default: number;
  timeframe_default: string;
  auto_refresh_seconds: number;
};

type RetentionItem = { table: string; ttl_days: number };

type Section = "profile" | "users" | "sso" | "general" | "retention" | "scoring";

const SECTIONS: { key: Section; label: string; adminOnly: boolean }[] = [
  { key: "profile",   label: "Your account",         adminOnly: false },
  { key: "users",     label: "Users & Access",       adminOnly: true },
  { key: "sso",       label: "Microsoft Entra SSO",  adminOnly: true },
  { key: "general",   label: "General",              adminOnly: true },
  { key: "retention", label: "Retention",            adminOnly: true },
  { key: "scoring",   label: "Suspicion scoring",    adminOnly: true },
];

export default function SettingsPage() {
  const toast = useToast();
  const [me, setMe] = useState<AppUser | null>(null);
  const [section, setSection] = useState<Section>("profile");

  // Settings sub-state
  const [weights, setWeights] = useState<ScoringWeights | null>(null);
  const [general, setGeneral] = useState<GeneralSettings | null>(null);
  const [retention, setRetention] = useState<RetentionItem[]>([]);
  const [savingScore, setSavingScore] = useState(false);
  const [savingGeneral, setSavingGeneral] = useState(false);
  const [savingRetention, setSavingRetention] = useState(false);

  useEffect(() => {
    meApi.get().then(setMe).catch(() => setMe(null));
  }, []);

  useEffect(() => {
    if (section === "scoring") {
      suspicionApi.getScoring().then(setWeights).catch(() => setWeights(null));
    } else if (section === "general") {
      api<GeneralSettings>("/settings").then(setGeneral).catch(() => setGeneral(null));
    } else if (section === "retention") {
      api<{ items: RetentionItem[] }>("/storage/retention").then((r) => setRetention(r.items)).catch(() => setRetention([]));
    }
  }, [section]);

  async function saveScoring() {
    if (!weights) return;
    setSavingScore(true);
    try {
      await suspicionApi.putScoring(weights);
      toast.push("Scoring weights saved", "success");
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 403 ? "Only admins can update scoring" : (e instanceof Error ? e.message : "Save failed");
      toast.push(msg, "danger");
    } finally {
      setSavingScore(false);
    }
  }

  async function saveGeneral() {
    if (!general) return;
    setSavingGeneral(true);
    try {
      await api("/settings", { method: "PUT", body: JSON.stringify(general) });
      toast.push("General settings saved", "success");
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 403 ? "Only admins can update settings" : (e instanceof Error ? e.message : "Save failed");
      toast.push(msg, "danger");
    } finally {
      setSavingGeneral(false);
    }
  }

  async function saveRetention() {
    setSavingRetention(true);
    try {
      const r = await api<{ items: RetentionItem[] }>("/storage/retention", {
        method: "PUT",
        body: JSON.stringify({ items: retention }),
      });
      setRetention(r.items);
      toast.push("Retention saved (TTLs altered on ClickHouse)", "success");
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 403 ? "Only admins can update retention" : (e instanceof Error ? e.message : "Save failed");
      toast.push(msg, "danger");
    } finally {
      setSavingRetention(false);
    }
  }

  const isAdmin = me?.role === "admin";
  const visibleSections = SECTIONS.filter((s) => !s.adminOnly || isAdmin);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">Settings</h1>
        <p className="text-xs text-muted">
          Signed in as <span className="text-text num">{me?.email ?? "—"}</span>
          {me && <span className="text-accent/70"> · {me.role}</span>}
          {!isAdmin && <span className="ml-2">· some sections require admin role</span>}
        </p>
      </div>

      <div className="grid lg:grid-cols-[200px_1fr] gap-6">
        {/* Vertical sub-nav */}
        <nav className="space-y-0.5">
          {visibleSections.map((s) => {
            const active = s.key === section;
            return (
              <button
                key={s.key}
                onClick={() => setSection(s.key)}
                className={
                  "w-full text-left px-3 py-2 rounded-md text-sm transition-colors " +
                  (active
                    ? "bg-accent/15 text-accent border border-accent/30"
                    : "text-text/80 hover:text-text hover:bg-panel2 border border-transparent")
                }
              >
                {s.label}
              </button>
            );
          })}
        </nav>

        {/* Section body */}
        <div className="min-w-0">
          {section === "profile" && <ProfilePanel onLoaded={setMe} />}
          {section === "users"   && isAdmin && <UsersPanel currentUserId={me!.id} />}
          {section === "sso"     && isAdmin && <SsoPanel />}

          {section === "general" && (
            <div className="panel p-5">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted mb-4">General</h2>
              {!general ? <div className="text-sm text-muted">Loading…</div> : (
                <div className="grid sm:grid-cols-2 gap-4">
                  <Field label="Collector max concurrent" hint="1-100">
                    <TextInput type="number" min={1} max={100} value={general.collector_max_concurrent}
                      onChange={(e) => setGeneral({ ...general, collector_max_concurrent: Number(e.target.value) })} />
                  </Field>
                  <Field label="Default polling interval (s)" hint="10-3600">
                    <TextInput type="number" min={10} max={3600} value={general.polling_interval_seconds_default}
                      onChange={(e) => setGeneral({ ...general, polling_interval_seconds_default: Number(e.target.value) })} />
                  </Field>
                  <Field label="Default timeframe">
                    <TextInput value={general.timeframe_default}
                      onChange={(e) => setGeneral({ ...general, timeframe_default: e.target.value })} />
                  </Field>
                  <Field label="Dashboard auto-refresh (s)" hint="5-600">
                    <TextInput type="number" min={5} max={600} value={general.auto_refresh_seconds}
                      onChange={(e) => setGeneral({ ...general, auto_refresh_seconds: Number(e.target.value) })} />
                  </Field>
                </div>
              )}
              <div className="mt-5">
                <button onClick={saveGeneral} disabled={!general || savingGeneral} className="btn btn-primary disabled:opacity-50">
                  {savingGeneral ? "Saving…" : "Save general"}
                </button>
              </div>
            </div>
          )}

          {section === "retention" && (
            <div className="panel p-5">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted mb-4">Retention (ClickHouse TTL, days)</h2>
              {retention.length === 0 ? <div className="text-sm text-muted">Loading…</div> : (
                <div className="grid sm:grid-cols-2 gap-3">
                  {retention.map((r, i) => (
                    <Field key={r.table} label={r.table}>
                      <TextInput type="number" min={1} max={36500} value={r.ttl_days}
                        onChange={(e) => {
                          const next = [...retention];
                          next[i] = { ...r, ttl_days: Number(e.target.value) };
                          setRetention(next);
                        }} />
                    </Field>
                  ))}
                </div>
              )}
              <div className="mt-5">
                <button onClick={saveRetention} disabled={savingRetention} className="btn btn-primary disabled:opacity-50">
                  {savingRetention ? "Saving…" : "Save retention"}
                </button>
                <p className="mt-2 text-xs text-muted">Changing TTL issues an <code>ALTER TABLE … MODIFY TTL</code> immediately.</p>
              </div>
            </div>
          )}

          {section === "scoring" && (
            <div className="panel p-5">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted mb-4">Suspicion scoring weights</h2>
              {!weights ? <div className="text-sm text-muted">Loading…</div> : (
                <div className="grid sm:grid-cols-2 gap-4">
                  {SCORING_KEYS.map((k) => (
                    <Field key={k} label={SCORING_LABEL[k]}>
                      <TextInput type="number" step="0.5" value={weights[k]}
                        onChange={(e) => setWeights({ ...weights, [k]: Number(e.target.value) })} />
                    </Field>
                  ))}
                </div>
              )}
              <div className="mt-5 flex items-center gap-2">
                <button onClick={saveScoring} disabled={!weights || savingScore} className="btn btn-primary disabled:opacity-50">
                  {savingScore ? "Saving…" : "Save weights"}
                </button>
                <button
                  onClick={() => weights && setWeights({
                    high_risk_event: 10, medium_risk_event: 5, low_risk_event: 1,
                    blocked_event: 4, repeated_client: 8, outbound_suspicious: 6,
                    malware_botnet: 15, large_transfer: 5, known_false_positive: -3,
                  })}
                  disabled={!weights}
                  className="btn"
                >
                  Reset to defaults
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
