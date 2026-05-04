"""/api/ipfix/sources — live ingestion-health view per branch.

Reads from `raw_flow_events` filtered to `collector_version='ipfix/0.1'`
and groups by branch_code so the operator can see which UDM Pro is
actively sending flows, when it last did, and how much data it's
generated. Branches that have never sent IPFIX show up as `inactive`
(via the LEFT JOIN against the `branches` table) so the page is also
useful as a "who's NOT exporting yet" punch list.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.clickhouse import client as ch
from app.models.user import User

router = APIRouter(prefix="/ipfix", tags=["ipfix"])


class IpfixSource(BaseModel):
    branch_id: str | None
    branch_code: str
    branch_name: str
    last_event_at: datetime | None
    rows_5m: int
    rows_1h: int
    rows_24h: int
    bytes_24h: int
    distinct_destinations_24h: int
    is_known_branch: bool


class IpfixSourcesResponse(BaseModel):
    items: list[IpfixSource]
    total_known_branches: int
    sending_now: int   # rows in last 5 minutes > 0


@router.get("/sources", response_model=IpfixSourcesResponse)
async def ipfix_sources(_user: User = Depends(get_current_user)) -> IpfixSourcesResponse:
    rows = await ch.query(
        """
        SELECT
            branch_id,
            branch_code,
            any(branch_name) AS branch_name,
            max(event_time)  AS last_event_at,
            countIf(event_time > now() - INTERVAL 5 MINUTE)  AS rows_5m,
            countIf(event_time > now() - INTERVAL 1 HOUR)    AS rows_1h,
            count()                                          AS rows_24h,
            sum(bytes_down + bytes_up)                       AS bytes_24h,
            uniq(destination_ip)                             AS distinct_destinations_24h
        FROM threatflow.raw_flow_events
        WHERE collector_version = 'ipfix/0.1'
          AND event_time > now() - INTERVAL 24 HOUR
        GROUP BY branch_id, branch_code
        ORDER BY rows_5m DESC, last_event_at DESC
        """
    )

    items: list[IpfixSource] = []
    for r in rows:
        bid_raw = r.get("branch_id")
        bid = str(bid_raw) if bid_raw else None
        items.append(IpfixSource(
            branch_id=bid,
            branch_code=str(r["branch_code"]),
            branch_name=str(r["branch_name"]),
            last_event_at=r.get("last_event_at"),
            rows_5m=int(r["rows_5m"]),
            rows_1h=int(r["rows_1h"]),
            rows_24h=int(r["rows_24h"]),
            bytes_24h=int(r["bytes_24h"]),
            distinct_destinations_24h=int(r["distinct_destinations_24h"]),
            # If branch_code starts with "unknown-" the WAN IP wasn't in
            # branch_wan_ips when ingested. Surface this so the operator
            # knows to populate the mapping.
            is_known_branch=not str(r["branch_code"]).startswith("unknown-"),
        ))

    return IpfixSourcesResponse(
        items=items,
        total_known_branches=len(items),
        sending_now=sum(1 for i in items if i.rows_5m > 0),
    )
