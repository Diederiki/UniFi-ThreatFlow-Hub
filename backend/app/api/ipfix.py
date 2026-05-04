"""/api/ipfix/sources — punch-list view of every enabled branch.

Reads ClickHouse for ingestion stats AND Postgres for the canonical
list of enabled branches, then merges so the operator sees:
  - Branches actively sending flows (live)
  - Branches that have sent flows but stopped
  - Branches that have NEVER sent flows (= still need their admin to
    enable IPFIX export pointing at us)
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from app.auth.dependencies import get_current_user
from app.clickhouse import client as ch
from app.db.session import SessionLocal
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
    is_enabled_branch: bool   # exists in PG branches.enabled=TRUE
    has_wan_ip_mapping: bool


class IpfixSourcesResponse(BaseModel):
    items: list[IpfixSource]
    total_enabled_branches: int       # all enabled cloud branches in PG
    total_with_data_24h: int          # branches that sent any flow in last 24h
    sending_now: int                  # rows in last 5 minutes > 0
    awaiting_admin: int               # enabled branches that have NEVER sent flows


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

    # PG: every enabled cloud-mode branch that should eventually be a source.
    async with SessionLocal() as db:
        pg_rows = (await db.execute(
            text(
                """
                SELECT b.id::text AS id, b.name, b.branch_code,
                  EXISTS(SELECT 1 FROM branch_wan_ips m WHERE m.branch_id = b.id) AS has_mapping
                FROM branches b
                WHERE b.enabled = TRUE
                  AND b.controller_url ILIKE '%unifi.ui.com%'
                ORDER BY b.name
                """
            )
        )).mappings().all()

    by_branch_id = {r["branch_id"]: dict(r) for r in rows if r.get("branch_id")}
    by_branch_code = {r["branch_code"]: dict(r) for r in rows}

    items: list[IpfixSource] = []
    seen_branch_ids: set[str] = set()

    for pg in pg_rows:
        bid = str(pg["id"])
        seen_branch_ids.add(bid)
        ch_row = by_branch_id.get(bid) or by_branch_code.get(pg["branch_code"])
        items.append(IpfixSource(
            branch_id=bid,
            branch_code=str(pg["branch_code"]),
            branch_name=str(pg["name"]),
            last_event_at=ch_row.get("last_event_at") if ch_row else None,
            rows_5m=int(ch_row["rows_5m"]) if ch_row else 0,
            rows_1h=int(ch_row["rows_1h"]) if ch_row else 0,
            rows_24h=int(ch_row["rows_24h"]) if ch_row else 0,
            bytes_24h=int(ch_row["bytes_24h"]) if ch_row else 0,
            distinct_destinations_24h=int(ch_row["distinct_destinations_24h"]) if ch_row else 0,
            is_known_branch=True,
            is_enabled_branch=True,
            has_wan_ip_mapping=bool(pg["has_mapping"]),
        ))

    # Add unknown-* sources (mirror, unmapped IPs) at the end of the list.
    for r in rows:
        bid_raw = r.get("branch_id")
        bid = str(bid_raw) if bid_raw else None
        if bid and bid in seen_branch_ids:
            continue
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
            is_known_branch=not str(r["branch_code"]).startswith("unknown-"),
            is_enabled_branch=False,
            has_wan_ip_mapping=False,
        ))

    # Sort: live first, then by recent activity, then awaiting (rows_24h=0) at the end.
    def sort_key(i: IpfixSource) -> tuple:
        return (
            -i.rows_5m,
            -i.rows_1h,
            -i.rows_24h,
            i.branch_name.lower(),
        )
    items.sort(key=sort_key)

    return IpfixSourcesResponse(
        items=items,
        total_enabled_branches=len(pg_rows),
        total_with_data_24h=sum(1 for i in items if i.rows_24h > 0 and i.is_enabled_branch),
        sending_now=sum(1 for i in items if i.rows_5m > 0),
        awaiting_admin=sum(1 for i in items if i.is_enabled_branch and i.rows_24h == 0),
    )
