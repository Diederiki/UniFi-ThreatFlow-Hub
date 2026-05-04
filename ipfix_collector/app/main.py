"""IPFIX/NetFlow v9 collector entry point.

Listens on UDP, parses each datagram, looks up branch by source IP,
maps each flow record to the existing `raw_flow_events` schema, and
batches into ClickHouse.

Built deliberately small + dependency-light: stdlib + asyncpg +
clickhouse-connect. The protocol parser lives in `parser.py` and is
~250 lines of hand-written code for maximum auditability.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import time

from app.branch_lookup import branch_cache
from app.ch_writer import writer
from app.config import settings
from app.mapper import map_record
from app.parser import ParseError, TemplateRegistry, parse_packet

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
log = logging.getLogger("ipfix.main")


class _UdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, registry: TemplateRegistry, on_records) -> None:
        self.registry = registry
        self.on_records = on_records
        self.packets_received = 0
        self.records_seen = 0
        self.parse_errors = 0
        self.unknown_exporters: dict[str, int] = {}

    def datagram_received(self, data: bytes, addr) -> None:
        host = addr[0]
        self.packets_received += 1
        try:
            records, _ = parse_packet(data, host, self.registry)
        except ParseError as e:
            self.parse_errors += 1
            log.debug("parse error from %s: %s", host, e)
            return
        if records:
            self.records_seen += len(records)
            self.on_records(host, records)


async def _stats_loop(proto: _UdpProtocol) -> None:
    while True:
        await asyncio.sleep(60)
        log.info(
            "stats: packets=%d records=%d errors=%d ch_inserted=%d ch_batches=%d ch_err=%d",
            proto.packets_received, proto.records_seen, proto.parse_errors,
            writer.rows_inserted, writer.batches, writer.errors,
        )


async def main_async() -> int:
    await writer.start()
    registry = TemplateRegistry()

    def on_records(exporter: str, records) -> None:
        # Run the per-record async pipeline as a fire-and-forget task; we
        # don't want to block the UDP receive callback.
        asyncio.create_task(_handle(exporter, records))

    async def _handle(exporter: str, records) -> None:
        try:
            branch = await branch_cache.for_source_ip(exporter)
        except Exception as e:
            log.warning("branch lookup error for %s: %s", exporter, e)
            return
        for rec in records:
            row = map_record(
                rec,
                branch_id=str(branch["id"]),
                branch_name=str(branch["name"]),
                branch_code=str(branch["branch_code"]),
            )
            await writer.submit(row)

    loop = asyncio.get_running_loop()
    transport, proto = await loop.create_datagram_endpoint(
        lambda: _UdpProtocol(registry, on_records),
        local_addr=(settings.bind_host, settings.bind_port),
        reuse_port=True,
    )
    log.info("listening UDP %s:%d for IPFIX/NetFlow v9",
             settings.bind_host, settings.bind_port)

    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    stats_task = asyncio.create_task(_stats_loop(proto))

    await stop.wait()
    log.info("shutting down")
    stats_task.cancel()
    transport.close()
    await writer.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
