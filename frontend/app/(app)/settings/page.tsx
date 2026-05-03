"use client";

import { useEffect, useState } from "react";
import { suspicionApi, type ScoringWeights } from "@/lib/suspicion";
import { Field, TextInput } from "@/components/forms/Field";
import { useToast } from "@/components/Toast";
import { ApiError } from "@/lib/api";

const LABEL: Record<keyof ScoringWeights, string> = {
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
const KEYS = Object.keys(LABEL) as (keyof ScoringWeights)[];

export default function SettingsPage() {
  const toast = useToast();
  const [weights, setWeights] = useState<ScoringWeights | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    suspicionApi.getScoring().then(setWeights).catch(() => setWeights(null));
  }, []);

  async function save() {
    if (!weights) return;
    setSaving(true);
    try {
      const updated = await suspicionApi.putScoring(weights);
      setWeights(updated);
      toast.push("Scoring weights saved", "success");
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 403 ? "Only admins can update scoring" : (e instanceof Error ? e.message : "Save failed");
      toast.push(msg, "danger");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-lg font-semibold">Settings</h1>
        <p className="text-xs text-muted">Suspicion scoring weights apply to all dashboards live · admin-only</p>
      </div>

      <div className="panel p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted mb-4">Suspicion scoring weights</h2>
        {!weights ? <div className="text-sm text-muted">Loading…</div> : (
          <div className="grid sm:grid-cols-2 gap-4">
            {KEYS.map((k) => (
              <Field key={k} label={LABEL[k]}>
                <TextInput
                  type="number"
                  step="0.5"
                  value={weights[k]}
                  onChange={(e) => setWeights({ ...weights, [k]: Number(e.target.value) })}
                />
              </Field>
            ))}
          </div>
        )}
        <div className="mt-5 flex items-center gap-2">
          <button onClick={save} disabled={!weights || saving} className="btn btn-primary disabled:opacity-50">
            {saving ? "Saving…" : "Save weights"}
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
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted mb-2 normal-case">More settings — coming in Phase 7</h2>
        <ul className="list-disc list-inside space-y-1">
          <li>Retention editor (per-table TTL)</li>
          <li>User + role management</li>
          <li>API key management</li>
          <li>Backup schedule + destination</li>
        </ul>
      </div>
    </div>
  );
}
