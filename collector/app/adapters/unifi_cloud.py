"""UnifiCloudAdapter — real Site Manager API poll (read-only).

Honest scope of the Ubiquiti Site Manager EA API (`api.ui.com/ea/...`):
  - List hosts / sites / devices
  - Per-site STATISTICS counters (totalDevice, wifiClient, wiredClient,
    internetIssues, gateway info, isp info, etc.)
  - Reachability / health

It does NOT expose per-flow or per-threat events. Flow/threat detail lives
behind the cloud proxy at unifi.ui.com which uses session auth, not the
public API key. So with API-key auth we can:

  ✅ confirm the branch is reachable → status='ok' + last_success_at
  ✅ report client/device counts as enrichment metadata
  ❌ generate raw_flow_events / raw_threat_events

When you eventually want per-flow ingestion you need either local-LAN access
to each UDM (LocalControllerAdapter) or a captured cloud-proxy session.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.adapters.base import BaseUniFiCollector, CollectResult
from app.config import COLLECTOR_VERSION, settings
from app.encryption import decrypt

log = logging.getLogger("collector.cloud")

SITE_MANAGER_BASE = "https://api.ui.com"


class UnifiCloudAdapter(BaseUniFiCollector):
    def __init__(self, branch: dict[str, Any]) -> None:
        super().__init__(branch)
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            from app.unifi_http import make_client
            self._client = make_client(timeout=settings.timeout_seconds)
        return self._client

    async def collect(self) -> CollectResult:
        result = CollectResult(
            endpoint_used=f"{SITE_MANAGER_BASE}/ea/sites",
            unifi_os_version=None, network_app_version=None,
        )
        api_key = decrypt(self.branch.get("encrypted_api_key"))
        if not api_key:
            raise RuntimeError("missing API key for cloud branch")

        headers = {"X-API-KEY": api_key, "Accept": "application/json"}
        client = self._get_client()
        r = await client.get(f"{SITE_MANAGER_BASE}/ea/sites", headers=headers)
        if r.status_code == 401 or r.status_code == 403:
            raise RuntimeError(f"api_key_rejected: http_{r.status_code}")
        if r.status_code != 200:
            raise RuntimeError(f"http_{r.status_code}: {r.text[:200]}")

        rows = (r.json().get("data") or [])
        # Find this branch's site by site_id
        site = next((s for s in rows if isinstance(s, dict) and s.get("siteId") == self.site_id), None)
        if site is None:
            raise RuntimeError(f"site_not_found_for_id: {self.site_id}")

        # Update result.network_app_version with a useful identifier so the
        # Collector Health page shows fresh info. We use the gateway shortname
        # (e.g. 'UDRULT') and isp name as recognizable info.
        stats = site.get("statistics") or {}
        gw = stats.get("gateway") if isinstance(stats, dict) else {}
        if isinstance(gw, dict):
            short = gw.get("shortname")
            if short:
                result.unifi_os_version = f"gateway/{short}"
        isp = stats.get("ispInfo") if isinstance(stats, dict) else {}
        if isinstance(isp, dict):
            org = isp.get("organization") or isp.get("name")
            if org:
                result.network_app_version = f"isp/{org}"

        # Site Manager API doesn't expose per-flow events through the public
        # endpoints. We return empty event lists — the dashboards will show
        # decreasing data as the existing CH events age out (TTL).
        # Status will tick to 'ok' and last_success_at refreshes every 30s,
        # which is what the user mainly wanted (real reachability signal).
        return result

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
