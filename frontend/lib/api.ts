// Browser-side API helper. Hits /api on the same origin (nginx routes it to FastAPI).
const BASE = process.env.NEXT_PUBLIC_API_BASE || "/api";

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: {
      "content-type": "application/json",
      ...(init.headers || {}),
    },
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
}
