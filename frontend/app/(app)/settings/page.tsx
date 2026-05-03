"use client";

import { useEffect, useState } from "react";
import { suspicionApi, type ScoringWeights } from "@/lib/suspicion";
import { Field, TextInput } from "@/components/forms/Field";
import { useToast } from "@/components/Toast";
import { api, ApiError } from "@/lib/api";

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

export default function SettingsPage() {
  const toast = useToast();
  const [weights, setWeights] = useState<ScoringWeights | null>(null);
  const [general, setGeneral] = useState<GeneralSettings | null>(null);
  const [retention, setRetention] = useState<RetentionItem[]>([]);
  const [savingScore, setSavingScore] = useState(false);
  const [savingGeneral, setSavingGeneral] = useState(false);
  const [savingRetention, setSavingRetention] = useState(false);

  useEffect(() => {
    suspicionApi.getScoring().then(setWeights).catch(() => setWeights(null));
    api<GeneralSettings>("/settings").then(setGeneral).catch(() => setGeneral(null));
    api<{ items: RetentionItem[] }>("/storage/retention").then((r) => setRetention(r.items)).catch(() => setRetention([]));
  }, []);

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

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-lg font-semibold">Settings</h1>
        <p className="text-xs text-muted">All sections are admin-only</p>
      </div>

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
          <span className="ml-3 text-xs text-muted">Changing TTL issues an `ALTER TABLE … MODIFY TTL` immediately.</span>
        </div>
      </div>

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

      <div className="panel p-5 text-xs text-muted">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted mb-2 normal-case">User / role management · API keys · Backup schedule</h2>
        <p className="mb-2">These surfaces aren't UI-driven yet. Today the equivalent operations are:</p>
        <ul className="list-disc list-inside space-y-1">
          <li>Add a user → run <code className="text-text">scripts/create-admin.sh</code> on the host with a different ADMIN_EMAIL</li>
          <li>Roles are seeded by Alembic (admin / operator / viewer); change a user's role via psql</li>
          <li>Backups: <code className="text-text">scripts/backup.sh</code> runs Postgres dump + ClickHouse FREEZE → tarball</li>
          <li>API keys: not yet implemented (Phase 8 candidate)</li>
        </ul>
      </div>
    </div>
  );
}
