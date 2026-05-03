"use client";

import { useEffect, useState } from "react";
import { meApi, type AppUser } from "@/lib/users";
import { Field, TextInput } from "@/components/forms/Field";
import { useToast } from "@/components/Toast";
import { ApiError } from "@/lib/api";

export function ProfilePanel({ onLoaded }: { onLoaded: (u: AppUser) => void }) {
  const toast = useToast();
  const [me, setMe] = useState<AppUser | null>(null);
  const [name, setName] = useState("");
  const [savingName, setSavingName] = useState(false);
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [savingPw, setSavingPw] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    meApi.get().then((u) => { setMe(u); setName(u.name ?? ""); onLoaded(u); }).catch(() => setMe(null));
  }, []);

  async function saveName() {
    setSavingName(true);
    try {
      const u = await meApi.updateProfile({ name });
      setMe(u);
      toast.push("Profile saved", "success");
    } catch (e) {
      toast.push(e instanceof Error ? e.message : "Save failed", "danger");
    } finally {
      setSavingName(false);
    }
  }

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    setSavingPw(true);
    try {
      await meApi.changePassword(cur, next);
      setCur(""); setNext("");
      toast.push("Password changed — other sessions invalidated", "success");
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail : "";
      const msg = detail === "current_password_incorrect" ? "Current password is wrong" : (err instanceof Error ? err.message : "Change failed");
      toast.push(msg, "danger");
    } finally {
      setSavingPw(false);
    }
  }

  async function signOutEverywhere() {
    if (!confirm("Sign out of every session, including this one?")) return;
    setSigningOut(true);
    try {
      await meApi.signOutEverywhere();
      window.location.href = "/login";
    } catch (e) {
      toast.push(e instanceof Error ? e.message : "Failed", "danger");
      setSigningOut(false);
    }
  }

  if (!me) return <div className="panel p-5 text-sm text-muted">Loading…</div>;

  return (
    <div className="panel p-5 space-y-5">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Your account</h2>

      <div className="grid sm:grid-cols-3 gap-3 text-sm">
        <div className="bg-panel2 rounded p-2"><div className="text-[10px] uppercase text-muted">Email</div><div className="num">{me.email}</div></div>
        <div className="bg-panel2 rounded p-2"><div className="text-[10px] uppercase text-muted">Role</div><div>{me.role}</div></div>
        <div className="bg-panel2 rounded p-2"><div className="text-[10px] uppercase text-muted">Auth method</div><div>{me.auth_method}{me.sso_subject ? " · sso bound" : ""}</div></div>
      </div>

      <div className="border-t border-border pt-4 space-y-3">
        <Field label="Display name">
          <div className="flex gap-2">
            <TextInput value={name} onChange={(e) => setName(e.target.value)} />
            <button onClick={saveName} disabled={savingName} className="btn text-xs disabled:opacity-50">
              {savingName ? "Saving…" : "Save"}
            </button>
          </div>
        </Field>
      </div>

      <form onSubmit={changePassword} className="border-t border-border pt-4 space-y-3">
        <h3 className="text-xs uppercase tracking-wide text-muted">Change your password</h3>
        <div className="grid sm:grid-cols-2 gap-3">
          <Field label="Current password" required>
            <TextInput type="password" autoComplete="current-password" required value={cur} onChange={(e) => setCur(e.target.value)} />
          </Field>
          <Field label="New password" required hint="Min 8 chars">
            <TextInput type="password" autoComplete="new-password" required minLength={8} value={next} onChange={(e) => setNext(e.target.value)} />
          </Field>
        </div>
        <button type="submit" disabled={savingPw} className="btn btn-primary text-xs disabled:opacity-50">
          {savingPw ? "Saving…" : "Change password"}
        </button>
        <p className="text-xs text-muted">Changing your password signs out every other session.</p>
      </form>

      <div className="border-t border-border pt-4">
        <button onClick={signOutEverywhere} disabled={signingOut} className="btn text-xs hover:text-danger disabled:opacity-50">
          {signingOut ? "Signing out…" : "Sign out everywhere"}
        </button>
        <p className="text-xs text-muted mt-1">Invalidates every JWT for your account, including this browser. You'll be redirected to login.</p>
      </div>
    </div>
  );
}
