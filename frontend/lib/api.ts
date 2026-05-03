// Browser-side API helper. Hits /api on the same origin (nginx routes it to FastAPI).
const BASE = process.env.NEXT_PUBLIC_API_BASE || "/api";
const DEFAULT_TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  // Hard timeout so a hung backend can't freeze the UI forever.
  const ctrl = new AbortController();
  const timeoutMs = (init as { timeoutMs?: number }).timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${BASE}${path}`, {
      credentials: "include",
      headers: {
        "content-type": "application/json",
        ...(init.headers || {}),
      },
      signal: ctrl.signal,
      ...init,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body?.detail ?? detail;
      } catch {}
      throw new ApiError(res.status, detail);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new ApiError(0, `request_timeout_${timeoutMs}ms`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}
