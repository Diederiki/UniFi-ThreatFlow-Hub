"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Field, Select, Switch, TextArea, TextInput } from "@/components/forms/Field";
import { useToast } from "@/components/Toast";
import { branchesApi, type Branch, type BranchCreateInput, type BranchUpdateInput, type TestConnectionResult } from "@/lib/branches";
import { ApiError } from "@/lib/api";

type Mode = { kind: "create" } | { kind: "edit"; branch: Branch };

type FormState = {
  name: string;
  branch_code: string;
  country: string;
  city: string;
  tags: string;            // comma-separated for the form
  controller_url: string;
  site_id: string;
  gateway_model: string;
  auth_method: "local" | "api_key";
  ssl_verify: boolean;
  polling_interval_seconds: number;
  enabled: boolean;
  notes: string;
  username: string;
  password: string;
  api_key: string;
  token: string;
};

function initialState(mode: Mode): FormState {
  if (mode.kind === "edit") {
    const b = mode.branch;
    return {
      name: b.name,
      branch_code: b.branch_code,
      country: b.country ?? "",
      city: b.city ?? "",
      tags: (b.tags ?? []).join(", "),
      controller_url: b.controller_url,
      site_id: b.site_id,
      gateway_model: b.gateway_model ?? "",
      auth_method: b.auth_method,
      ssl_verify: b.ssl_verify,
      polling_interval_seconds: b.polling_interval_seconds,
      enabled: b.enabled,
      notes: b.notes ?? "",
      username: "",
      password: "",
      api_key: "",
      token: "",
    };
  }
  return {
    name: "",
    branch_code: "",
    country: "",
    city: "",
    tags: "",
    controller_url: "https://",
    site_id: "default",
    gateway_model: "",
    auth_method: "local",
    ssl_verify: true,
    polling_interval_seconds: 30,
    enabled: true,
    notes: "",
    username: "",
    password: "",
    api_key: "",
    token: "",
  };
}

export function BranchForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const toast = useToast();
  const [s, setS] = useState<FormState>(() => initialState(mode));
  const [submitting, setSubmitting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null);

  function patch<K extends keyof FormState>(key: K, value: FormState[K]) {
    setS((prev) => ({ ...prev, [key]: value }));
  }

  function buildPayload(): BranchCreateInput {
    const tags = s.tags.split(",").map((t) => t.trim()).filter(Boolean);
    const credentials = {
      username: s.username || null,
      password: s.password || null,
      api_key: s.api_key || null,
      token: s.token || null,
    };
    return {
      name: s.name.trim(),
      branch_code: s.branch_code.trim(),
      country: s.country.trim() || null,
      city: s.city.trim() || null,
      tags,
      controller_url: s.controller_url.trim(),
      site_id: s.site_id.trim() || "default",
      gateway_model: s.gateway_model.trim() || null,
      auth_method: s.auth_method,
      ssl_verify: s.ssl_verify,
      polling_interval_seconds: s.polling_interval_seconds,
      enabled: s.enabled,
      notes: s.notes.trim() || null,
      credentials,
    };
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const payload = buildPayload();
      const branch = mode.kind === "create"
        ? await branchesApi.create(payload)
        : await branchesApi.update(mode.branch.id, payload as BranchUpdateInput);
      toast.push(mode.kind === "create" ? "Branch created" : "Branch updated", "success");
      router.push(`/branches/${branch.id}`);
    } catch (e) {
      const msg =
        e instanceof ApiError && e.status === 409
          ? "branch_code already exists"
          : e instanceof ApiError && e.status === 403
            ? "Only admins/operators can save branches"
            : e instanceof Error ? e.message : "Save failed";
      toast.push(msg, "danger");
    } finally {
      setSubmitting(false);
    }
  }

  async function onTest() {
    if (mode.kind !== "edit") {
      toast.push("Save first, then test the live connection", "warn");
      return;
    }
    setTesting(true);
    try {
      const r = await branchesApi.test(mode.branch.id);
      setTestResult(r);
      toast.push(r.ok ? `OK · ${r.endpoint_used}${r.is_mock ? " (mock)" : ""}` : `Failed: ${r.error}`, r.ok ? "success" : "danger");
    } catch (e) {
      toast.push(e instanceof Error ? e.message : "Test failed", "danger");
    } finally {
      setTesting(false);
    }
  }

  async function onDiscover() {
    if (mode.kind !== "edit") {
      toast.push("Save first, then discover sites", "warn");
      return;
    }
    setTesting(true);
    try {
      const r = await branchesApi.discover(mode.branch.id);
      setTestResult(r);
      if (r.ok) toast.push(`Discovered ${r.sites_discovered.length} site(s)`, "success");
      else toast.push(`Discover failed: ${r.error}`, "danger");
    } catch (e) {
      toast.push(e instanceof Error ? e.message : "Discover failed", "danger");
    } finally {
      setTesting(false);
    }
  }

  const isEdit = mode.kind === "edit";
  const credsMeta = isEdit ? mode.branch.credentials_meta : { has_username: false, has_password: false, has_api_key: false, has_token: false };

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      <div className="grid lg:grid-cols-3 gap-6">
        <section className="panel p-5 space-y-4 lg:col-span-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">Identity</h2>
          <div className="grid sm:grid-cols-2 gap-4">
            <Field label="Branch name" required>
              <TextInput value={s.name} onChange={(e) => patch("name", e.target.value)} placeholder="HQ Singapore" required />
            </Field>
            <Field label="Branch code" required hint="Letters / numbers / dash / underscore. Used in URLs and exports.">
              <TextInput value={s.branch_code} onChange={(e) => patch("branch_code", e.target.value)} placeholder="SGP01" required pattern="[A-Za-z0-9_\-]+" />
            </Field>
            <Field label="Country">
              <TextInput value={s.country} onChange={(e) => patch("country", e.target.value)} placeholder="Singapore" />
            </Field>
            <Field label="City">
              <TextInput value={s.city} onChange={(e) => patch("city", e.target.value)} placeholder="Singapore" />
            </Field>
            <Field label="Tags" hint="Comma-separated, e.g. apac, prod" className="sm:col-span-2">
              <TextInput value={s.tags} onChange={(e) => patch("tags", e.target.value)} placeholder="apac, prod" />
            </Field>
          </div>
        </section>

        <section className="panel p-5 space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">State</h2>
          <Field label="Enabled">
            <Switch checked={s.enabled} onChange={(v) => patch("enabled", v)} label={s.enabled ? "Polling" : "Paused"} />
          </Field>
          <Field label="Polling interval (seconds)" hint="10–3600">
            <TextInput type="number" min={10} max={3600} value={s.polling_interval_seconds}
              onChange={(e) => patch("polling_interval_seconds", Number(e.target.value))} />
          </Field>
          <Field label="Gateway model">
            <Select value={s.gateway_model} onChange={(e) => patch("gateway_model", e.target.value)}>
              <option value="">— unspecified —</option>
              <option>UDM Pro</option>
              <option>UDM Pro Max</option>
              <option>UDM SE</option>
              <option>UXG Pro</option>
              <option>Other</option>
            </Select>
          </Field>
        </section>
      </div>

      <section className="panel p-5 space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">UniFi controller</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <Field label="Controller URL" required hint="e.g. https://192.168.1.1 or https://unifi.branch.example.com" className="sm:col-span-2">
            <TextInput type="url" value={s.controller_url} onChange={(e) => patch("controller_url", e.target.value)} required />
          </Field>
          <Field label="Site ID" hint="Often `default` unless you renamed it">
            <TextInput value={s.site_id} onChange={(e) => patch("site_id", e.target.value)} required />
          </Field>
          <Field label="Auth method">
            <Select value={s.auth_method} onChange={(e) => patch("auth_method", e.target.value as "local" | "api_key")}>
              <option value="local">local user</option>
              <option value="api_key">api key</option>
            </Select>
          </Field>
          <Field label="Verify SSL?" hint="Off only if the controller has a self-signed cert">
            <Switch checked={s.ssl_verify} onChange={(v) => patch("ssl_verify", v)} label={s.ssl_verify ? "verify" : "skip"} />
          </Field>
        </div>
      </section>

      <section className="panel p-5 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">Credentials</h2>
          <span className="text-xs text-muted">Encrypted at rest with Fernet. Leave a field blank to keep its current value.</span>
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="Username" hint={credsMeta.has_username ? "stored — leave blank to keep" : "not set"}>
            <TextInput autoComplete="off" value={s.username} onChange={(e) => patch("username", e.target.value)} placeholder={credsMeta.has_username ? "••••••" : ""} />
          </Field>
          <Field label="Password" hint={credsMeta.has_password ? "stored — leave blank to keep" : "not set"}>
            <TextInput type="password" autoComplete="new-password" value={s.password} onChange={(e) => patch("password", e.target.value)} placeholder={credsMeta.has_password ? "••••••" : ""} />
          </Field>
          <Field label="API key" hint={credsMeta.has_api_key ? "stored — leave blank to keep" : "optional"}>
            <TextInput autoComplete="off" value={s.api_key} onChange={(e) => patch("api_key", e.target.value)} placeholder={credsMeta.has_api_key ? "••••••" : ""} />
          </Field>
          <Field label="Bearer token" hint={credsMeta.has_token ? "stored — leave blank to keep" : "optional"}>
            <TextInput autoComplete="off" value={s.token} onChange={(e) => patch("token", e.target.value)} placeholder={credsMeta.has_token ? "••••••" : ""} />
          </Field>
        </div>
      </section>

      <section className="panel p-5 space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">Notes</h2>
        <TextArea value={s.notes} onChange={(e) => patch("notes", e.target.value)} placeholder="Anything the next admin should know" />
      </section>

      {testResult && (
        <section className={`panel p-5 border-2 ${testResult.ok ? "border-success/50" : "border-danger/50"}`}>
          <div className="flex items-center gap-2 mb-2">
            <span className={`text-xs font-semibold uppercase ${testResult.ok ? "text-success" : "text-danger"}`}>
              {testResult.ok ? "✓ Connection OK" : "✗ Connection failed"}
            </span>
            {testResult.is_mock && <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-warn/15 text-warn border border-warn/30">mock</span>}
            <span className="text-xs text-muted ml-auto num">{testResult.duration_ms} ms</span>
          </div>
          {testResult.endpoint_used && <div className="text-xs text-muted">endpoint: <span className="num text-text">{testResult.endpoint_used}</span></div>}
          {testResult.unifi_os_version && <div className="text-xs text-muted">UniFi OS: <span className="text-text">{testResult.unifi_os_version}</span></div>}
          {testResult.sites_discovered.length > 0 && <div className="text-xs text-muted">sites: <span className="text-text">{testResult.sites_discovered.join(", ")}</span></div>}
          {testResult.error && <div className="text-xs text-danger mt-1">{testResult.error}</div>}
        </section>
      )}

      <div className="flex flex-wrap items-center gap-2 pt-2">
        <button type="submit" disabled={submitting} className="btn btn-primary disabled:opacity-50">
          {submitting ? "Saving…" : isEdit ? "Save branch" : "Save & start collector"}
        </button>
        <button type="button" disabled={!isEdit || testing} onClick={onTest} className="btn disabled:opacity-50">
          {testing ? "Testing…" : "Test connection"}
        </button>
        <button type="button" disabled={!isEdit || testing} onClick={onDiscover} className="btn disabled:opacity-50">
          Discover sites
        </button>
        <button type="button" onClick={() => router.back()} className="btn ml-auto">Cancel</button>
      </div>
    </form>
  );
}
