"""ClickHouse client wrapper.

`clickhouse-connect`'s sync Client is NOT thread-safe — two concurrent calls
on the same instance raise `Attempt to execute concurrent queries within the
same session`. So we create a fresh Client per call. The cost is minimal
because urllib3's PoolManager is class-level inside the driver, so the
underlying TCP connection pool IS shared.

Calls are wrapped in `asyncio.to_thread` so the event loop stays free.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterable, Sequence

import clickhouse_connect
from clickhouse_connect.driver.client import Client as CHClient

from app.config import settings

log = logging.getLogger(__name__)


def _new_client() -> CHClient:
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_http_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_db,
        compress=True,
        connect_timeout=10,
        send_receive_timeout=60,
    )


async def query(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    def _do():
        c = _new_client()
        try:
            result = c.query(sql, parameters=params or {})
            cols = result.column_names
            return [dict(zip(cols, row)) for row in result.result_rows]
        finally:
            try: c.close()
            except Exception: pass
    return await asyncio.to_thread(_do)


async def query_one(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rows = await query(sql, params)
    return rows[0] if rows else None


async def execute(sql: str, params: dict[str, Any] | None = None) -> None:
    def _do():
        c = _new_client()
        try:
            c.command(sql, parameters=params or {})
        finally:
            try: c.close()
            except Exception: pass
    await asyncio.to_thread(_do)


async def insert_batch(table: str, rows: Sequence[dict[str, Any]], column_names: Iterable[str] | None = None) -> int:
    """Batch insert. Returns number of rows submitted."""
    if not rows:
        return 0
    cols = list(column_names) if column_names else list(rows[0].keys())
    data = [[r.get(c) for c in cols] for r in rows]

    def _do():
        c = _new_client()
        try:
            c.insert(table=table, data=data, column_names=cols)
            return len(data)
        finally:
            try: c.close()
            except Exception: pass
    return await asyncio.to_thread(_do)


async def ping() -> bool:
    def _do():
        c = _new_client()
        try:
            c.command("SELECT 1")
            return True
        finally:
            try: c.close()
            except Exception: pass
    try:
        return await asyncio.to_thread(_do)
    except Exception as e:  # noqa: BLE001
        log.warning("clickhouse ping failed: %s", e)
        return False

