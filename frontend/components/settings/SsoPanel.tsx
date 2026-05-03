"use client";

import { useEffect, useState } from "react";
import { ssoApi, type SsoConfig, type Role } from "@/lib/users";
import { Field, Select, Switch, TextInput } from "@/components/forms/Field";
import { useToast } from "@/components/Toast";
import { ApiError } from "@/lib/api";

const ROLES: Role[] = ["admin", "operator", "viewer"];

export function SsoPanel() {
  const toast = useToast();
  const [cfg, setCfg] = useState<SsoConfig | null>(null);
  const [secret, setSecret] = useState("");        // empty = keep existing
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    ssoApi.getConfig().then(setCfg).catch(() => setCfg(null));
  }, []);

  // Sensible default redirect URI based on the current host
  useEffect(() => {
    if (!cfg) return;
    if (!cfg.redirect_uri) {
      const url = `${window.location.origin}/api/auth/sso/callback`;
      setCfg({ ...cfg, redirect_uri: url });
    }
  }, [cfg?.tenant_id]);  // eslint-disable-line

  async function save() {
    if (!cfg) return;
    setSaving(true);
    try {
      const updated = await ssoApi.putConfig({
        enabled: cfg.enabled,
        tenant_id: cfg.tenant_id,
        client_id: cfg.client_id,
        client_secret: secret,        // empty = keep existing
        redirect_uri: cfg.redirect_uri,
        auto_provision: cfg.auto_provision,
        default_role: cfg.default_role,
      });
      setCfg(updated);
      setSecret("");
      toast.push("SSO config saved", "success");
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 403 ? "Only admins can configure SSO" : (e instanceof Error ? e.message : "Save failed");
      toast.push(msg, "danger");
    } finally {
      setSaving(false);
    }
  }

  if (!cfg) return <div className="panel p-5 text-sm text-muted">Loading SSO config…</div>;

  return (
    <div className="panel p-5 space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Microsoft Entra (Azure AD) SSO</h2>
        <Switch checked={cfg.enabled} onChange={(v) => setCfg({ ...cfg, enabled: v })} label={cfg.enabled ? "ENABLED" : "disabled"} />
      </div>

      <p className="text-xs text-muted">
        Register an App in <span className="text-text">Entra ID → App registrations</span>. Add a Web platform with the Redirect URI shown below. Generate a client secret. Required API permissions: <code className="text-text">openid</code>, <code className="text-text">profile</code>, <code className="text-text">email</code>.
      </p>

      <div className="grid sm:grid-cols-2 gap-4">
        <Field label="Tenant ID" hint="GUID from your Entra tenant overview">
          <TextInput value={cfg.tenant_id} onChange={(e) => setCfg({ ...cfg, tenant_id: e.target.value })}
            placeholder="00000000-0000-0000-0000-000000000000" />
        </Field>
        <Field label="Application (client) ID">
          <TextInput value={cfg.client_id} onChange={(e) => setCfg({ ...cfg, client_id: e.target.value })}
            placeholder="00000000-0000-0000-0000-000000000000" />
        </Field>
        <Field label="Client secret" hint={cfg.has_client_secret ? "stored — leave blank to keep" : "value shown to Entra app, never to users"} className="sm:col-span-2">
          <TextInput type="password" autoComplete="new-password" value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder={cfg.has_client_secret ? "••••••••••••" : "paste from Entra"} />
        </Field>
        <Field label="Redirect URI" hint="Copy this exact value into Entra → Authentication → Web → Redirect URIs" className="sm:col-span-2">
          <TextInput value={cfg.redirect_uri} onChange={(e) => setCfg({ ...cfg, redirect_uri: e.target.value })}
            placeholder="https://threatflow.amspec.group/api/auth/sso/callback" />
        </Field>
        <Field label="Auto-provision new users" hint="Off: only existing users can sign in via SSO">
          <Switch checked={cfg.auto_provision} onChange={(v) => setCfg({ ...cfg, auto_provision: v })} />
        </Field>
        <Field label="Default role for auto-provisioned users">
          <Select value={cfg.default_role} onChange={(e) => setCfg({ ...cfg, default_role: e.target.value as Role })}>
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </Select>
        </Field>
      </div>

      <div className="flex items-center gap-2">
        <button onClick={save} disabled={saving} className="btn btn-primary disabled:opacity-50">
          {saving ? "Saving…" : "Save SSO config"}
        </button>
        {cfg.enabled && cfg.tenant_id && cfg.client_id && cfg.has_client_secret && (
          <a href="/api/auth/sso/start" className="btn text-xs" target="_self">Test sign-in</a>
        )}
      </div>
    </div>
  );
}
