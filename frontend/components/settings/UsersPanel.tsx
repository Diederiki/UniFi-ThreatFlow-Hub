"use client";

import { useEffect, useState } from "react";
import { usersApi, type AppUser, type Role } from "@/lib/users";
import { Field, Select, Switch, TextInput } from "@/components/forms/Field";
import { useToast } from "@/components/Toast";
import { ApiError } from "@/lib/api";

const ROLES: Role[] = ["admin", "operator", "viewer"];

function roleColor(r: Role): string {
  if (r === "admin") return "bg-danger/15 text-danger border-danger/30";
  if (r === "operator") return "bg-warn/15 text-warn border-warn/30";
  return "bg-panel2 text-muted border-border";
}

function fmtDate(iso: string | null): string {
  if (!iso) return "never";
  return new Date(iso).toLocaleString();
}

function NewUserDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (u: AppUser) => void }) {
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [password, setPassword] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  function genPassword() {
    const chars = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#$%";
    let s = ""; for (let i = 0; i < 16; i++) s += chars[Math.floor(Math.random() * chars.length)];
    setPassword(s);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const u = await usersApi.create({ email, name: name || null, role, enabled, password });
      toast.push(`User ${u.email} created`, "success");
      onCreated(u); onClose();
    } catch (err) {
      const msg = err instanceof ApiError && err.status === 409 ? "Email already exists" : (err instanceof Error ? err.message : "Create failed");
      toast.push(msg, "danger");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center px-4">
      <form onSubmit={submit} className="panel p-5 max-w-md w-full space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">New user</h2>
        <Field label="Email" required>
          <TextInput type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="user@amspecgroup.com" />
        </Field>
        <Field label="Name">
          <TextInput value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Role">
          <Select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </Select>
        </Field>
        <Field label="Enabled">
          <Switch checked={enabled} onChange={setEnabled} />
        </Field>
        <Field label="Password" hint="Min 8 chars">
          <div className="flex gap-2">
            <TextInput required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
            <button type="button" onClick={genPassword} className="btn text-xs">Generate</button>
          </div>
        </Field>
        <div className="flex gap-2 justify-end pt-2">
          <button type="button" onClick={onClose} className="btn text-xs">Cancel</button>
          <button type="submit" disabled={submitting} className="btn btn-primary text-xs disabled:opacity-50">
            {submitting ? "Creating…" : "Create user"}
          </button>
        </div>
      </form>
    </div>
  );
}

function ResetPasswordDialog({ user, onClose }: { user: AppUser; onClose: () => void }) {
  const toast = useToast();
  const [pw, setPw] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await usersApi.resetPassword(user.id, pw);
      toast.push(`Password reset for ${user.email} — their existing sessions are invalidated`, "success");
      onClose();
    } catch (err) {
      toast.push(err instanceof Error ? err.message : "Reset failed", "danger");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center px-4">
      <form onSubmit={submit} className="panel p-5 max-w-md w-full space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Reset password — {user.email}</h2>
        <p className="text-xs text-muted">All existing sessions for this user will be invalidated.</p>
        <Field label="New password" required hint="Min 8 chars">
          <TextInput type="password" required minLength={8} value={pw} onChange={(e) => setPw(e.target.value)} />
        </Field>
        <div className="flex gap-2 justify-end pt-2">
          <button type="button" onClick={onClose} className="btn text-xs">Cancel</button>
          <button type="submit" disabled={submitting} className="btn btn-primary text-xs disabled:opacity-50">
            {submitting ? "Saving…" : "Reset password"}
          </button>
        </div>
      </form>
    </div>
  );
}

export function UsersPanel({ currentUserId }: { currentUserId: number }) {
  const toast = useToast();
  const [items, setItems] = useState<AppUser[] | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [resetting, setResetting] = useState<AppUser | null>(null);

  async function reload() {
    try {
      const r = await usersApi.list();
      setItems(r.items);
    } catch (e) {
      toast.push(e instanceof Error ? e.message : "Load failed", "danger");
    }
  }

  useEffect(() => { reload(); }, []);

  async function setRole(u: AppUser, role: Role) {
    try {
      const updated = await usersApi.update(u.id, { role });
      setItems((arr) => arr?.map((x) => (x.id === u.id ? updated : x)) ?? arr);
      toast.push(`${u.email} → ${role}`, "success");
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 400 ? "Cannot demote the last admin" : (e instanceof Error ? e.message : "Update failed");
      toast.push(msg, "danger");
    }
  }

  async function toggleEnabled(u: AppUser) {
    try {
      const updated = await usersApi.update(u.id, { enabled: !u.enabled });
      setItems((arr) => arr?.map((x) => (x.id === u.id ? updated : x)) ?? arr);
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 400 ? "Cannot disable the last admin" : (e instanceof Error ? e.message : "Update failed");
      toast.push(msg, "danger");
    }
  }

  async function del(u: AppUser) {
    if (!confirm(`Delete ${u.email}? This is irreversible.`)) return;
    try {
      await usersApi.delete(u.id);
      setItems((arr) => arr?.filter((x) => x.id !== u.id) ?? arr);
      toast.push(`${u.email} deleted`, "success");
    } catch (e) {
      const detail = e instanceof ApiError ? e.detail : "";
      const friendly = detail === "cannot_delete_self" ? "Cannot delete yourself"
        : detail === "cannot_delete_last_admin" ? "Cannot delete the last admin"
        : (e instanceof Error ? e.message : "Delete failed");
      toast.push(friendly, "danger");
    }
  }

  return (
    <div className="panel p-5 space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Users &amp; Access</h2>
        <button onClick={() => setShowNew(true)} className="btn btn-primary text-xs">+ New user</button>
      </div>

      {!items ? (
        <div className="text-sm text-muted">Loading…</div>
      ) : items.length === 0 ? (
        <div className="text-sm text-muted">No users yet.</div>
      ) : (
        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted border-b border-border">
              <tr>
                <th className="text-left px-2 py-2 font-medium">Email</th>
                <th className="text-left px-2 py-2 font-medium">Name</th>
                <th className="text-left px-2 py-2 font-medium">Role</th>
                <th className="text-left px-2 py-2 font-medium">Auth</th>
                <th className="text-left px-2 py-2 font-medium">Last login</th>
                <th className="text-left px-2 py-2 font-medium">State</th>
                <th className="text-right px-2 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((u) => (
                <tr key={u.id} className="border-b border-border last:border-b-0">
                  <td className="px-2 py-2 text-xs">{u.email}{u.id === currentUserId && <span className="ml-1 text-[10px] text-accent">(you)</span>}</td>
                  <td className="px-2 py-2 text-xs">{u.name || "—"}</td>
                  <td className="px-2 py-2">
                    <select value={u.role} onChange={(e) => setRole(u, e.target.value as Role)}
                      className={`text-[11px] px-1.5 py-0.5 rounded-md border ${roleColor(u.role)} bg-transparent`}>
                      {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </td>
                  <td className="px-2 py-2 text-xs text-muted">
                    {u.auth_method}{u.sso_subject ? " · sso bound" : ""}
                  </td>
                  <td className="px-2 py-2 text-xs text-muted">{fmtDate(u.last_login_at)}</td>
                  <td className="px-2 py-2">
                    <button onClick={() => toggleEnabled(u)}
                      className={"text-[11px] px-1.5 py-0.5 rounded-md border " + (u.enabled ? "bg-success/15 text-success border-success/30" : "bg-panel2 text-muted border-border")}>
                      {u.enabled ? "enabled" : "disabled"}
                    </button>
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex justify-end gap-1.5">
                      <button onClick={() => setResetting(u)} className="btn text-xs">Reset pw</button>
                      <button onClick={() => del(u)} className="btn text-xs hover:text-danger" disabled={u.id === currentUserId}>Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showNew && <NewUserDialog onClose={() => setShowNew(false)} onCreated={(u) => setItems((arr) => arr ? [...arr, u] : [u])} />}
      {resetting && <ResetPasswordDialog user={resetting} onClose={() => setResetting(null)} />}
    </div>
  );
}
