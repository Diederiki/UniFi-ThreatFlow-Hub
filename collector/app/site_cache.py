"""Per-tick cache for the Site Manager `/ea/sites` response.

Site Manager's `/ea/sites` returns the full set of sites visible to the API key
in one call. Without this cache, every branch's UnifiCloudAdapter fetches that
same endpoint independently — 55 branches → 55 identical requests per 30s tick,
and Site Manager rate-limits ~15% of them with HTTP 429 each cycle, which makes
those branches flicker offline in the dashboard.

A fresh SiteManagerCache is created at the start of every scheduler tick and
shared with all adapters dispatched in that tick. The first adapter to need
the data fetches it; the rest await the cached `{siteId: site}` map. One
HTTP call per (api_key, tick) instead of one per branch.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

SITE_MANAGER_BASE = "https://api.ui.com"


class SiteManagerCache:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._sites: dict[str, dict[str, dict[str, Any]]] = {}

    async def get(self, api_key: str, client: httpx.AsyncClient) -> dict[str, dict[str, Any]]:
        """Return a `{siteId: site}` map for this api_key, fetching once per tick."""
        if api_key in self._sites:
            return self._sites[api_key]
        async with self._lock:
            if api_key in self._sites:
                return self._sites[api_key]
            headers = {"X-API-KEY": api_key, "Accept": "application/json"}
            r = await client.get(f"{SITE_MANAGER_BASE}/ea/sites", headers=headers)
            if r.status_code in (401, 403):
                raise RuntimeError(f"api_key_rejected: http_{r.status_code}")
            if r.status_code != 200:
                raise RuntimeError(f"http_{r.status_code}: {r.text[:200]}")
            rows = r.json().get("data") or []
            sites_by_id = {
                s["siteId"]: s
                for s in rows
                if isinstance(s, dict) and s.get("siteId")
            }
            self._sites[api_key] = sites_by_id
            return sites_by_id
