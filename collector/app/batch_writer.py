"""Batched ClickHouse insert. Two queues — flows + threats — drained either
when they reach CH_BATCH_SIZE or every CH_FLUSH_INTERVAL_MS, whichever first.
On insert failure: exponential backoff up to CH_INSERT_RETRIES, then dump to
the `failed_inserts` table so nothing is silently lost."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from app.config import settings
from app.db import ch

log = logging.getLogger("collector.writer")

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

THREAT_COLS = [
    "event_hash", "branch_id", "branch_name", "branch_code",
    "event_time", "action", "severity", "risk",
    "signature", "threat_category",
    "policy_type", "policy_name",
    "source_ip", "source_port", "source_mac", "source_hostname",
    "destination_ip", "destination_port", "destination_hostname", "destination_country",
    "protocol",
    "client_ip", "client_mac", "client_hostname",
    "raw_json", "collector_version",
]


class BatchWriter:
    def __init__(self) -> None:
        self._flows: list[dict[str, Any]] = []
        self._threats: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._flusher: asyncio.Task[None] | None = None

    async def submit_flows(self, rows: list[dict[str, Any]]) -> None:
        async with self._lock:
            self._flows.extend(rows)
            if len(self._flows) >= settings.ch_batch_size:
                await self._flush_flows_locked()

    async def submit_threats(self, rows: list[dict[str, Any]]) -> None:
        async with self._lock:
            self._threats.extend(rows)
            if len(self._threats) >= settings.ch_batch_size:
                await self._flush_threats_locked()

    async def _flush_flows_locked(self) -> None:
        if not self._flows:
            return
        batch, self._flows = self._flows, []
        await self._insert_with_retry("raw_flow_events", batch, FLOW_COLS)

    async def _flush_threats_locked(self) -> None:
        if not self._threats:
            return
        batch, self._threats = self._threats, []
        await self._insert_with_retry("raw_threat_events", batch, THREAT_COLS)

    async def _insert_with_retry(self, table: str, rows: list[dict[str, Any]], cols: list[str]) -> None:
        attempt = 0
        last_err: Exception | None = None
        while attempt <= settings.ch_insert_retries:
            try:
                n = await ch.insert(table, rows, cols)
                log.info("ch insert ok table=%s rows=%d attempt=%d", table, n, attempt + 1)
                return
            except Exception as e:  # noqa: BLE001
                last_err = e
                attempt += 1
                if attempt > settings.ch_insert_retries:
                    break
                wait = min(2 ** attempt, 30)
                log.warning("ch insert failed table=%s rows=%d attempt=%d err=%s — retry in %ds",
                            table, len(rows), attempt, e, wait)
                await asyncio.sleep(wait)
        log.error("ch insert giving up table=%s rows=%d err=%s — writing dead-letter", table, len(rows), last_err)
        sample = json.dumps(rows[0], default=str) if rows else ""
        branch = str(rows[0].get("branch_id", "")) if rows else ""
        await ch.write_failure(table, branch, len(rows), str(last_err), sample)

    async def _flush_loop(self) -> None:
        interval = max(0.05, settings.ch_flush_interval_ms / 1000.0)
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
            async with self._lock:
                await self._flush_flows_locked()
                await self._flush_threats_locked()

    async def start(self) -> None:
        if self._flusher is None:
            self._flusher = asyncio.create_task(self._flush_loop())

    async def shutdown(self) -> None:
        self._stop.set()
        if self._flusher:
            await self._flusher
        async with self._lock:
            await self._flush_flows_locked()
            await self._flush_threats_locked()


writer = BatchWriter()
