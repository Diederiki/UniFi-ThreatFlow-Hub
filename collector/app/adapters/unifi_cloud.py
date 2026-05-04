"""UnifiCloudAdapter — speaks the unifi.ui.com cloud portal API.

Architecture note (Phase 2 finding): the user accesses every branch through
the Ubiquiti cloud portal at unifi.ui.com — not direct controller URLs. So
one Ubiquiti SSO login can enumerate every console and pull flow data without
per-branch credentials.

Phase 4 ships the auth + structure scaffolding. Live integration depends on
capturing the exact request flow from DevTools (see README "IMPORTANT UNIFI
ENDPOINT NOTE").
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.adapters.base import BaseUniFiCollector, CollectResult
from app.config import settings
from app.encryption import decrypt

log = logging.getLogger("collector.cloud")

SSO_BASE = "https://account.ui.com"
API_BASE = "https://api.ui.com"


class UnifiCloudAdapter(BaseUniFiCollector):
    def __init__(self, branch: dict[str, Any]) -> None:
        super().__init__(branch)
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            from app.unifi_http import make_client
            self._client = make_client(timeout=settings.timeout_seconds)
        return self._client

    async def _login(self, client: httpx.AsyncClient) -> None:
        username = decrypt(self.branch.get("encrypted_username"))
        password = decrypt(self.branch.get("encrypted_password"))
        if not username or not password:
            raise RuntimeError("missing Ubiquiti SSO username/password")

        r = await client.post(
            f"{SSO_BASE}/api/sso/v1/user/login",
            json={"username": username, "password": password},
        )
        # MFA challenges return 499 / 401 with a 2FA token — Phase 4.x will handle.
        r.raise_for_status()

    async def collect(self) -> CollectResult:
        result = CollectResult(
            endpoint_used=f"unifi-cloud://consoles/{self.controller_url}/network/{self.site_id}/insights/flows",
        )
        client = self._get_client()
        try:
            await self._login(client)
            # The flow data lives behind the `proxy.networkflow` API — captured live
            # from DevTools the path is approximately:
            #   GET https://api.ui.com/proxy/.../consoles/{console_id}/network/api/s/{site}/insights/flows
            # Phase 4.x will materialize the parser once we have a captured har file.
            log.info("unifi-cloud login OK for %s — parser TBD", self.branch_code)
        except httpx.HTTPError as e:
            log.warning("unifi-cloud login failed for %s: %s", self.branch_code, e)
            raise
        return result

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
