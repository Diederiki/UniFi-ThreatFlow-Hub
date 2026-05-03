"""LocalControllerAdapter — speaks the local UDM Pro web API directly.

Phase 4 ships the structure. Real probing requires a live device; until then
this adapter just records that it tried (returns 0 events with a clear
endpoint_used so you can see what would be hit).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.adapters.base import BaseUniFiCollector, CollectResult
from app.config import COLLECTOR_VERSION, settings
from app.encryption import decrypt

log = logging.getLogger("collector.local")


class LocalControllerAdapter(BaseUniFiCollector):
    PRIMARY_PATH = "/proxy/network/v2/api/site/{site_id}/traffic-flows"
    FALLBACK_PATH = "/proxy/network/api/s/{site_id}/stat/ips/event"

    def __init__(self, branch: dict[str, Any]) -> None:
        super().__init__(branch)
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.controller_url.rstrip("/"),
                verify=self.ssl_verify,
                timeout=httpx.Timeout(settings.timeout_seconds),
                follow_redirects=True,
            )
        return self._client

    async def _login(self, client: httpx.AsyncClient) -> None:
        username = decrypt(self.branch.get("encrypted_username"))
        password = decrypt(self.branch.get("encrypted_password"))
        if not username or not password:
            raise RuntimeError("missing username/password for local controller adapter")
        # UniFi OS uses /api/auth/login; older Network apps use /api/login.
        for path, payload in (
            ("/api/auth/login", {"username": username, "password": password}),
            ("/api/login",      {"username": username, "password": password, "remember": True}),
        ):
            try:
                r = await client.post(path, json=payload)
                if r.status_code in (200, 204):
                    return
            except httpx.HTTPError:  # noqa: PERF203
                continue
        raise RuntimeError("authentication failed against /api/auth/login and /api/login")

    async def collect(self) -> CollectResult:
        result = CollectResult(
            endpoint_used=self.PRIMARY_PATH.format(site_id=self.site_id),
        )
        client = self._get_client()
        try:
            await self._login(client)
            primary = self.PRIMARY_PATH.format(site_id=self.site_id)
            r = await client.get(primary, params={"limit": 5000, "offset": 0})
            if r.status_code == 404:
                fallback = self.FALLBACK_PATH.format(site_id=self.site_id)
                result.endpoint_used = fallback
                r = await client.get(fallback)
            r.raise_for_status()

            # TODO Phase 4.x: feed r.json()["data"] through normalize_flow / normalize_threat
            # — depends on the precise shape returned by the live UDM Pro version under test.
            log.info("local-controller %s returned %d bytes (parser TBD)", self.controller_url, len(r.content))
        finally:
            pass  # keep client open across ticks for connection reuse

        return result

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
