"""Batched ClickHouse writer that submits IPFIX-derived rows to
`raw_flow_events` using the standard FLOW_COLS column order shared with
the existing collector / cloudproxy ingest paths."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from clickhouse_connect import get_async_client

from app.config import settings

log = logging.getLogger("ipfix.ch")

FLOW_COLS = [
    "event_hash", "branch_id", "branch_name", "branch_code",
    "event_time", "action", "risk", "severity",
    "policy_type", "policy_name",
    "source_ip", "source_port", "source_mac", "source_hostname", "source_vlan",
    "destination_ip", "destination_port", "destination_hostname", "destination_country",
    "protocol", "application", "application_category",
    "bytes_up", "bytes_down", "packets_up", "packets_down",
    "duration_ms", "direction", "raw_json", "collector_version",
]


class ChWriter:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._buf: list[dict[str, Any]] = []
        self._client = None
        self._stop = asyncio.Event()
        self._flusher: asyncio.Task | None = None
        self.rows_inserted = 0
        self.batches = 0
        self.errors = 0

    async def start(self) -> None:
        self._client = await get_async_client(
            host=settings.ch_host, port=settings.ch_port,
            database=settings.ch_db,
            username=settings.ch_user, password=settings.ch_pwd,
        )
        self._flusher = asyncio.create_task(self._flush_loop())
        log.info("ch writer started → %s:%d/%s", settings.ch_host, settings.ch_port, settings.ch_db)

    async def submit(self, row: dict[str, Any]) -> None:
        async with self._lock:
            self._buf.append(row)
            if len(self._buf) >= settings.batch_size:
                await self._flush_locked()

    async def _flush_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=settings.flush_ms / 1000.0)
                return
            except asyncio.TimeoutError:
                async with self._lock:
                    if self._buf:
                        await self._flush_locked()

    async def _flush_locked(self) -> None:
        batch, self._buf = self._buf, []
        if not batch:
            return
        try:
            data = [[r.get(c) for c in FLOW_COLS] for r in batch]
            assert self._client is not None
            await self._client.insert(
                table="raw_flow_events", data=data, column_names=FLOW_COLS,
            )
            self.rows_inserted += len(batch)
            self.batches += 1
        except Exception as e:
            self.errors += 1
            log.warning("ch insert failed (%d rows): %s", len(batch), e)

    async def shutdown(self) -> None:
        self._stop.set()
        if self._flusher:
            await self._flusher
        async with self._lock:
            await self._flush_locked()
        if self._client:
            await self._client.close()


writer = ChWriter()
