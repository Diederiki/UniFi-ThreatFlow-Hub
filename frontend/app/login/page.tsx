"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";

const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "UniFi Threatflow Hub for AmSpec";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      router.replace("/overview");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Invalid email or password.");
      } else {
        setError(err instanceof Error ? err.message : "Login failed.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm panel p-6 shadow-glow">
        <div className="mb-6">
          <div className="text-xs uppercase tracking-widest text-muted mb-1">Sign in</div>
          <h1 className="text-xl font-semibold">{APP_NAME}</h1>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-muted mb-1" htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input"
              placeholder="you@amspecgroup.com"
            />
          </div>

          <div>
            <label className="block text-xs text-muted mb-1" htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input"
              placeholder="••••••••••••"
            />
          </div>

          {error && (
            <div className="text-sm text-danger bg-danger/10 border border-danger/30 rounded-md px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="btn btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="mt-6 text-xs text-muted text-center">
          Restricted access. All actions are audit-logged.
        </p>
      </div>
    </main>
  );
}
