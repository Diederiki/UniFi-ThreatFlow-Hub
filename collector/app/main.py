"""Phase 1 heartbeat — proves the container boots, picks up env, logs at the
configured cadence. Phase 4 replaces this with the real adapter system,
scheduler, dedupe, and ClickHouse batch writer.
"""
import asyncio
import logging
import signal
from contextlib import suppress

from app.config import settings


def setup_logging() -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-5s collector :: %(message)s",
    )


async def heartbeat() -> None:
    log = logging.getLogger("collector")
    log.info(
        "heartbeat-only mode (Phase 1) — interval=%ds, mock=%s, env=%s",
        settings.interval_seconds, settings.mock_data, settings.app_env,
    )
    while True:
        log.info("tick — Phase 4 will replace this with real polling")
        await asyncio.sleep(settings.interval_seconds)


async def amain() -> None:
    setup_logging()
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()

    def _shutdown() -> None:
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, _shutdown)

    task = asyncio.create_task(heartbeat())
    await stop.wait()
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


if __name__ == "__main__":
    asyncio.run(amain())
