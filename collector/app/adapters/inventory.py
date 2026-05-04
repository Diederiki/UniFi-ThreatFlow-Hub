"""Periodic client + device inventory adapters per blueprint § Data Fetching.

These adapters fetch enrichment data (MAC → hostname, device list) once per N
ticks rather than every tick — that data changes slowly and we just need it
for richer joins on dashboards. Phase 4 ships the structure; live UniFi
parsing lands when a device is wired up.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.adapters.base import BaseUniFiCollector, CollectResult
from app.config import settings

log = logging.getLogger("collector.inventory")


class UniFiClientInventoryCollector(BaseUniFiCollector):
    PATH = "/proxy/network/api/s/{site_id}/stat/sta"

    def __init__(self, branch: dict[str, Any]) -> None:
        super().__init__(branch)
        self._client: httpx.AsyncClient | None = None

    async def collect(self) -> CollectResult:
        # Inventory is enrichment, not events — return empty event lists.
        # The structure is in place so a real implementation can replace this.
        # Always read-only, like every other UniFi call in the collector.
        endpoint = self.PATH.format(site_id=self.site_id)
        log.debug("client inventory probe %s (parser TBD, read-only GET)", endpoint)
        return CollectResult(endpoint_used=endpoint)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


class UniFiDeviceInventoryCollector(BaseUniFiCollector):
    PATH = "/proxy/network/api/s/{site_id}/stat/device"

    def __init__(self, branch: dict[str, Any]) -> None:
        super().__init__(branch)
        self._client: httpx.AsyncClient | None = None

    async def collect(self) -> CollectResult:
        # Read-only GET only.
        endpoint = self.PATH.format(site_id=self.site_id)
        log.debug("device inventory probe %s (parser TBD, read-only GET)", endpoint)
        return CollectResult(endpoint_used=endpoint)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
