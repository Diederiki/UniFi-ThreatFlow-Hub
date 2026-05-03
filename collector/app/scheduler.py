"""30s scheduler with concurrency cap + per-branch Redis lock.

Each tick:
  1. Loads all enabled branches from PG.
  2. For each branch, dispatches a coroutine that takes the global semaphore,
     acquires a per-branch lock in Redis (so a slow branch can't pile up),
     calls the right adapter, hashes/dedupes events, batches them to CH, and
     records a collector_run + collector_status row.
  3. A failing branch never stops other branches.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from uuid import UUID

import redis.asyncio as redis

from app.adapters import select_adapter
from app.batch_writer import writer
from app.config import COLLECTOR_VERSION, settings
from app.db import pg
from app.dedupe import event_hash

log = logging.getLogger("collector.sched")


class Scheduler:
    def __init__(self) -> None:
        self._sem = asyncio.Semaphore(settings.max_concurrent)
        self._redis = redis.Redis(
            host=settings.redis_host, port=settings.redis_port,
            password=settings.redis_password or None,
            decode_responses=True,
        )

    def _lock_key(self, branch_id: UUID | str) -> str:
        return f"threatflow:lock:branch:{branch_id}"

    async def _try_lock(self, branch_id: str) -> bool:
        return bool(await self._redis.set(
            self._lock_key(branch_id),
            "1",
            nx=True,
            ex=settings.timeout_seconds + 5,
        ))

    async def _release_lock(self, branch_id: str) -> None:
        await self._redis.delete(self._lock_key(branch_id))

    async def _process_branch(self, branch: dict[str, Any]) -> None:
        bid = str(branch["id"])
        async with self._sem:
            if not await self._try_lock(bid):
                log.info("branch %s skipped (lock held — previous tick still running)", branch["branch_code"])
                return
            run_id = await pg.open_run(branch["id"])
            started = time.perf_counter()
            adapter = select_adapter(branch)
            status = "ok"
            err: str | None = None
            event_count = 0
            endpoint_used: str | None = None
            unifi_os_v = network_app_v = None

            try:
                result = await asyncio.wait_for(adapter.collect(), timeout=settings.timeout_seconds)
                endpoint_used = result.endpoint_used
                unifi_os_v = result.unifi_os_version
                network_app_v = result.network_app_version

                # Hash + dedupe per blueprint
                for evt in result.flows:
                    evt["event_hash"] = event_hash(evt)
                for evt in result.threats:
                    evt["event_hash"] = event_hash(evt)

                if result.flows:
                    await writer.submit_flows(result.flows)
                if result.threats:
                    await writer.submit_threats(result.threats)

                event_count = result.event_count
                log.info("branch %s collected %d events via %s", branch["branch_code"], event_count, endpoint_used)
            except asyncio.TimeoutError:
                status = "error"
                err = f"timeout after {settings.timeout_seconds}s"
                log.warning("branch %s timed out", branch["branch_code"])
            except Exception as e:  # noqa: BLE001
                status = "error"
                err = f"{type(e).__name__}: {e}"
                log.exception("branch %s collect failed", branch["branch_code"])
            finally:
                duration_ms = int((time.perf_counter() - started) * 1000)
                await pg.close_run(
                    run_id=run_id, branch_id=branch["id"], status=status,
                    event_count=event_count, error_message=err,
                    endpoint_used=endpoint_used, duration_ms=duration_ms,
                    unifi_os_version=unifi_os_v, network_app_version=network_app_v,
                    collector_version=COLLECTOR_VERSION,
                )
                await self._release_lock(bid)
                await adapter.close()

    async def tick(self) -> None:
        branches = await pg.list_enabled_branches()
        if not branches:
            log.info("tick: no enabled branches")
            return
        log.info("tick: dispatching %d branch(es)", len(branches))
        await asyncio.gather(*[self._process_branch(b) for b in branches], return_exceptions=False)

    async def run_forever(self) -> None:
        await writer.start()
        try:
            while True:
                started = time.perf_counter()
                try:
                    await self.tick()
                except Exception:  # noqa: BLE001
                    log.exception("tick raised; continuing")
                elapsed = time.perf_counter() - started
                sleep_for = max(1.0, settings.interval_seconds - elapsed)
                await asyncio.sleep(sleep_for)
        finally:
            await writer.shutdown()
            await self._redis.close()
