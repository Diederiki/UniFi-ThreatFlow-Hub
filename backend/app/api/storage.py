"""/api/storage endpoints — reads ClickHouse system tables to surface row
counts, on-disk size, freshness, and TTL settings; ALTERs TTLs on PUT."""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user, require_role
from app.clickhouse import client as ch
from app.config import settings
from app.models.user import User
from app.schemas.storage import (
    RetentionList,
    RetentionPolicy,
    RetentionUpdate,
    StorageHealth,
    TableHealth,
)

router = APIRouter(prefix="/storage", tags=["storage"])

TRACKED_TABLES = [
    "raw_flow_events",
    "raw_threat_events",
    "rollup_1m",
    "rollup_5m",
    "rollup_15m",
    "rollup_1h",
    "rollup_1d",
]
TIME_COL = {
    "raw_flow_events": "event_time",
    "raw_threat_events": "event_time",
    "rollup_1m": "window_start",
    "rollup_5m": "window_start",
    "rollup_15m": "window_start",
    "rollup_1h": "window_start",
    "rollup_1d": "window_start",
}


async def _table_health(name: str) -> TableHealth | None:
    db = settings.clickhouse_db
    parts = await ch.query_one(
        """
        SELECT
            sum(rows)             AS rows,
            sum(bytes_on_disk)    AS bytes_on_disk,
            sum(data_uncompressed_bytes) AS bytes_uncompressed,
            count()               AS parts
        FROM system.parts
        WHERE database = {db:String} AND table = {tbl:String} AND active
        """,
        {"db": db, "tbl": name},
    )
    if not parts or (parts.get("rows") or 0) == 0:
        # table exists but empty
        exists = await ch.query_one(
            "SELECT count() AS c FROM system.tables WHERE database = {db:String} AND name = {tbl:String}",
            {"db": db, "tbl": name},
        )
        if not exists or exists.get("c", 0) == 0:
            return None
        return TableHealth(
            name=name, rows=0, bytes_on_disk=0, bytes_uncompressed=0,
            compression_ratio=None, parts=0,
        )

    rows = int(parts.get("rows") or 0)
    bod = int(parts.get("bytes_on_disk") or 0)
    bun = int(parts.get("bytes_uncompressed") or 0)
    ratio = round(bun / bod, 2) if bod > 0 else None

    time_col = TIME_COL.get(name)
    oldest = newest = None
    if time_col and rows > 0:
        time_row = await ch.query_one(
            f"SELECT min({time_col}) AS oldest, max({time_col}) AS newest FROM {db}.{name}"
        )
        if time_row:
            oldest = time_row.get("oldest")
            newest = time_row.get("newest")

    return TableHealth(
        name=name,
        rows=rows,
        bytes_on_disk=bod,
        bytes_uncompressed=bun,
        compression_ratio=ratio,
        parts=int(parts.get("parts") or 0),
        oldest_event=oldest,
        newest_event=newest,
    )


@router.get("/health", response_model=StorageHealth)
async def storage_health(_user: User = Depends(get_current_user)) -> StorageHealth:
    if not await ch.ping():
        return StorageHealth(clickhouse_ok=False)

    health = StorageHealth(clickhouse_ok=True)
    for tbl in TRACKED_TABLES:
        setattr(health, tbl, await _table_health(tbl))

    failed = await ch.query_one(
        "SELECT count() AS c FROM threatflow.failed_inserts WHERE failed_at > now() - INTERVAL 30 DAY"
    )
    health.failed_inserts_30d = int(failed.get("c", 0)) if failed else 0

    if health.rollup_1m and health.rollup_1m.newest_event:
        delta = await ch.query_one(
            "SELECT toUInt32(now() - max(window_start)) AS d FROM threatflow.rollup_1m"
        )
        if delta:
            health.rollup_freshness_1m_seconds = int(delta.get("d") or 0)

    if health.rollup_1d and health.rollup_1d.rows > 0:
        per_day = await ch.query_one(
            "SELECT round(avg(t)) AS d FROM (SELECT sumMerge(total_flows) AS t FROM threatflow.rollup_1d "
            "WHERE window_start > now() - INTERVAL 14 DAY GROUP BY window_start)"
        )
        if per_day:
            health.events_per_day_estimate = int(per_day.get("d") or 0)

    return health


# ---- Retention -------------------------------------------------------------

_TTL_RE = re.compile(r"INTERVAL\s+(\d+)\s+DAY", re.IGNORECASE)


async def _current_ttls() -> list[RetentionPolicy]:
    rows = await ch.query(
        "SELECT name, engine_full FROM system.tables "
        "WHERE database = {db:String} AND name IN ({names:Array(String)})",
        {"db": settings.clickhouse_db, "names": TRACKED_TABLES},
    )
    items: list[RetentionPolicy] = []
    by_name = {r["name"]: r["engine_full"] for r in rows}
    for tbl in TRACKED_TABLES:
        engine = by_name.get(tbl, "") or ""
        m = _TTL_RE.search(engine)
        days = int(m.group(1)) if m else 0
        items.append(RetentionPolicy(table=tbl, ttl_days=days))
    return items


@router.get("/retention", response_model=RetentionList)
async def get_retention(_user: User = Depends(get_current_user)) -> RetentionList:
    return RetentionList(items=await _current_ttls())


@router.put("/retention", response_model=RetentionList)
async def put_retention(
    payload: RetentionUpdate,
    _user: User = Depends(require_role("admin")),
) -> RetentionList:
    db = settings.clickhouse_db
    for item in payload.items:
        if item.table not in TRACKED_TABLES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"unknown_table:{item.table}")
        if item.ttl_days < 1 or item.ttl_days > 36500:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="ttl_days_out_of_range")

        time_col = TIME_COL[item.table]
        if item.table.startswith("raw_"):
            ttl_clause = f"toDateTime({time_col}) + INTERVAL {item.ttl_days} DAY DELETE"
        else:
            ttl_clause = f"{time_col} + INTERVAL {item.ttl_days} DAY DELETE"
        await ch.execute(f"ALTER TABLE {db}.{item.table} MODIFY TTL {ttl_clause}")

    return RetentionList(items=await _current_ttls())
