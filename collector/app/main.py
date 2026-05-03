"""Collector entry point.

Replaces the Phase 1 heartbeat with the real pipeline:
  scheduler.tick() every COLLECTOR_INTERVAL_SECONDS
    └─ select_adapter(branch).collect()
        └─ event_hash + batch_writer.submit_*()
            └─ ClickHouse batch insert (or dead-letter on failure)
  status writes go to PG collector_runs + collector_status.
"""
import asyncio
import logging
import signal
from contextlib import suppress

from app.config import COLLECTOR_VERSION, settings
from app.scheduler import Scheduler


def setup_logging() -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-5s %(name)s :: %(message)s",
    )


async def amain() -> None:
    setup_logging()
    log = logging.getLogger("collector")
    log.info(
        "starting collector v%s (interval=%ds, max_concurrent=%d, mock=%s, env=%s)",
        COLLECTOR_VERSION, settings.interval_seconds, settings.max_concurrent,
        settings.mock_data, settings.app_env,
    )

    sched = Scheduler()
    main_task = asyncio.create_task(sched.run_forever())

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    log.info("shutdown signal received")
    main_task.cancel()
    with suppress(asyncio.CancelledError):
        await main_task


if __name__ == "__main__":
    asyncio.run(amain())
