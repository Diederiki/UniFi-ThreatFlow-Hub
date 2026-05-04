"""Map source IP (the UDM's NAT'd public IP) → ThreatFlow branch row.

We periodically read the `branches` + `branch_credentials` tables and
build an in-memory cache keyed by the WAN IP that the UDM is exporting
from. Until we know an IP belongs to a known branch we fall back to a
synthesised "unknown:<ip>" branch_code so the data still lands and the
operator can wire it up later.

`branches.controller_url` doesn't directly contain WAN IPs (it's the
unifi.ui.com console URL), so we depend on a separate lookup table
`branch_wan_ips` populated by `infra/sql/branch_wan_ips.sql` for the
production rollout. If that table doesn't exist we degrade gracefully
to the unknown-branch fallback.
"""
from __future__ import annotations

import asyncio
import logging
import time
from uuid import UUID, uuid5, NAMESPACE_DNS

import asyncpg

from app.config import settings

log = logging.getLogger("ipfix.lookup")

UNKNOWN_NS = uuid5(NAMESPACE_DNS, "ipfix.unknown.threatflow")


class BranchCache:
    def __init__(self) -> None:
        self._by_ip: dict[str, dict] = {}
        self._fetched_at: float = 0.0
        self._lock = asyncio.Lock()

    async def _refresh(self) -> None:
        async with self._lock:
            if time.time() - self._fetched_at < settings.branch_lookup_refresh_seconds:
                return
            conn = await asyncpg.connect(
                host=settings.pg_host, port=settings.pg_port,
                database=settings.pg_db, user=settings.pg_user,
                password=settings.pg_pwd,
            )
            try:
                # Try the optional ipfix mapping table first.
                rows = await conn.fetch(
                    """
                    SELECT b.id::text AS id, b.name, b.branch_code, m.wan_ip
                    FROM branch_wan_ips m
                    JOIN branches b ON b.id = m.branch_id
                    """
                ) if await self._table_exists(conn, "branch_wan_ips") else []
            finally:
                await conn.close()
            self._by_ip = {r["wan_ip"]: dict(r) for r in rows}
            self._fetched_at = time.time()
            log.info("branch lookup refreshed: %d wan-ip mappings", len(self._by_ip))

    async def _table_exists(self, conn: asyncpg.Connection, name: str) -> bool:
        return await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = $1)",
            name,
        )

    async def for_source_ip(self, src_ip: str) -> dict:
        if not self._by_ip or time.time() - self._fetched_at >= settings.branch_lookup_refresh_seconds:
            try:
                await self._refresh()
            except Exception as e:
                log.warning("branch refresh failed: %s — using cached/empty mapping", e)
        rec = self._by_ip.get(src_ip)
        if rec:
            return rec
        # Synthesise a stable unknown-branch identity from the source IP.
        synth_id = str(uuid5(UNKNOWN_NS, src_ip))
        return {
            "id": synth_id,
            "name": f"Unknown ({src_ip})",
            "branch_code": f"unknown-{src_ip.replace('.', '-')}",
        }


branch_cache = BranchCache()
