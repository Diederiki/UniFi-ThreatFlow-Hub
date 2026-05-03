"""ClickHouse client for the collector. Same shape as the backend wrapper."""
from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any, Iterable, Sequence

import clickhouse_connect
from clickhouse_connect.driver.client import Client as CHClient

from app.config import settings


@lru_cache(maxsize=1)
def _client() -> CHClient:
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


async def insert(table: str, rows: Sequence[dict[str, Any]], cols: Iterable[str]) -> int:
    if not rows:
        return 0
    column_names = list(cols)
    data = [[r.get(c) for c in column_names] for r in rows]

    def _do() -> int:
        _client().insert(table=table, data=data, column_names=column_names)
        return len(data)
    return await asyncio.to_thread(_do)


async def write_failure(target: str, branch_id: str, rows: int, error: str, sample: str) -> None:
    def _do() -> None:
        _client().insert(
            table="failed_inserts",
            data=[[target, branch_id, rows, error, sample[:1000]]],
            column_names=["target", "branch_id", "rows", "error", "payload_sample"],
        )
    try:
        await asyncio.to_thread(_do)
    except Exception:  # noqa: BLE001
        pass  # if the dead-letter table is unreachable too, swallow
