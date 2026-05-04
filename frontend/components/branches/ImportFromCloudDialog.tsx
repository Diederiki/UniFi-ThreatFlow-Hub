"use client";

import { useState } from "react";
import { branchesApi, type ImportSummary } from "@/lib/branches";
import { Field, TextInput } from "@/components/forms/Field";
import { useToast } from "@/components/Toast";
import { ApiError } from "@/lib/api";

export function ImportFromCloudDialog({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: () => void;
}) {
  const toast = useToast();
  const [apiKey, setApiKey] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ImportSummary | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const r = await branchesApi.importFromCloud(apiKey);
      setResult(r);
      onImported();
      if (r.created === 0 && r.failed === 0) {
        toast.push(`${r.skipped_existing} sites already exist as branches — nothing to do`, "info");
      } else {
        toast.push(`Imported ${r.created} new branch(es) · ${r.skipped_existing} skipped · ${r.failed} failed`, r.failed > 0 ? "warn" : "success");
      }
    } catch (err) {
      const msg =
        err instanceof ApiError && err.status === 403
          ? "Only admins/operators can import"
          : err instanceof Error ? err.message : "Import failed";
      toast.push(msg, "danger");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center px-4">
      <div className="panel p-5 max-w-lg w-full space-y-3 max-h-[90vh] overflow-y-auto">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Import all sites from Site Manager</h2>

        {!result ? (
          <form onSubmit={submit} className="space-y-3">
            <p className="text-xs text-muted">
              Paste an API key from <span className="text-text">unifi.ui.com → Site Manager → Admin → API</span>.
              We'll fetch every site you have access to and create one Threatflow branch per site,
              all sharing this key. Re-running is safe (existing branches are skipped).
            </p>
            <p className="text-xs text-muted">
              <span className="text-success">Read-only:</span> ThreatFlow only ever issues GET requests to UniFi.
              Even so, we recommend a key scoped read-only on the Ubiquiti side.
            </p>
            <Field label="Site Manager API key" required>
              <TextInput
                type="password"
                autoComplete="off"
                required
                minLength={8}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="paste from Ubiquiti — never re-shown"
              />
            </Field>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={onClose} className="btn text-xs">Cancel</button>
              <button type="submit" disabled={submitting || apiKey.length < 8} className="btn btn-primary text-xs disabled:opacity-50">
                {submitting ? "Importing…" : "Import all sites"}
              </button>
            </div>
          </form>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="bg-panel2 rounded p-2">
                <div className="text-[10px] uppercase text-muted">Sites seen</div>
                <div className="num text-lg">{result.total_seen.toLocaleString()}</div>
              </div>
              <div className="bg-panel2 rounded p-2">
                <div className="text-[10px] uppercase text-muted">Created</div>
                <div className="num text-lg text-success">{result.created.toLocaleString()}</div>
              </div>
              <div className="bg-panel2 rounded p-2">
                <div className="text-[10px] uppercase text-muted">Already existed</div>
                <div className="num text-lg text-muted">{result.skipped_existing.toLocaleString()}</div>
              </div>
              <div className={`rounded p-2 ${result.failed > 0 ? "bg-danger/10 border border-danger/30" : "bg-panel2"}`}>
                <div className="text-[10px] uppercase text-muted">Failed</div>
                <div className={`num text-lg ${result.failed > 0 ? "text-danger" : ""}`}>{result.failed.toLocaleString()}</div>
              </div>
            </div>
            {result.errors.length > 0 && (
              <div className="text-xs text-danger max-h-40 overflow-y-auto">
                <div className="text-muted mb-1">Errors:</div>
                <ul className="list-disc list-inside space-y-1">
                  {result.errors.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              </div>
            )}
            <div className="flex justify-end pt-2">
              <button onClick={onClose} className="btn btn-primary text-xs">Done</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
