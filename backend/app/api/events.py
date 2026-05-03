"""/api/threats and /api/blocked — paginated event tables with filters.
These read from raw tables (with time bounds) since they need per-event detail.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.auth.dependencies import get_current_user
from app.clickhouse import client as ch
from app.models.user import User
from app.schemas.dashboard import EventsPage, FlowEvent, ThreatEvent
from app.utils.timeframe import parse

router = APIRouter(tags=["events"])


def _flow_select(extra_where: list[str] | None = None) -> str:
    where = ["event_time >= {since:DateTime64(3,'UTC')}", "event_time < {until:DateTime64(3,'UTC')}"]
    if extra_where:
        where.extend(extra_where)
    return f"""
        SELECT
            toString(event_id) AS event_id, event_hash,
            branch_code, branch_name, event_time,
            action, risk, severity, policy_type, policy_name,
            source_ip, source_hostname,
            destination_ip, destination_port, destination_hostname, destination_country,
            protocol, application, application_category,
            bytes_up, bytes_down
        FROM threatflow.raw_flow_events
        WHERE {" AND ".join(where)}
        ORDER BY event_time DESC
        LIMIT {{limit:UInt32}} OFFSET {{offset:UInt32}}
    """


@router.get("/threats", response_model=EventsPage)
async def list_threats(
    timeframe: str = Query(default="24h"),
    branch_id: UUID | None = Query(default=None),
    severity: str | None = Query(default=None, description="low / medium / high / critical"),
    signature: str | None = Query(default=None),
    source_ip: str | None = Query(default=None),
    destination_ip: str | None = Query(default=None),
    action: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    _user: User = Depends(get_current_user),
):
    tf = parse(timeframe)
    where = ["event_time >= {since:DateTime64(3,'UTC')}", "event_time < {until:DateTime64(3,'UTC')}"]
    params: dict[str, Any] = {"since": tf.since, "until": tf.until}
    if branch_id:
        where.append("branch_id = {bid:UUID}"); params["bid"] = branch_id
    if severity:
        where.append("severity = {sev:String}"); params["sev"] = severity
    if signature:
        where.append("positionCaseInsensitive(signature, {sig:String}) > 0"); params["sig"] = signature
    if source_ip:
        where.append("source_ip = {sip:String}"); params["sip"] = source_ip
    if destination_ip:
        where.append("destination_ip = {dip:String}"); params["dip"] = destination_ip
    if action:
        where.append("action = {act:String}"); params["act"] = action

    offset = (page - 1) * page_size
    params["limit"] = page_size
    params["offset"] = offset

    sql = f"""
        SELECT
            toString(event_id) AS event_id, event_hash,
            branch_code, branch_name, event_time,
            action, risk, severity, policy_type, policy_name,
            source_ip, source_hostname,
            destination_ip, destination_port, destination_hostname, destination_country,
            protocol, signature, threat_category, client_ip,
            0 AS bytes_up, 0 AS bytes_down,
            '' AS application, '' AS application_category
        FROM threatflow.raw_threat_events
        WHERE {" AND ".join(where)}
        ORDER BY event_time DESC
        LIMIT {{limit:UInt32}} OFFSET {{offset:UInt32}}
    """
    rows = await ch.query(sql, params)
    items = [ThreatEvent(**r) for r in rows]
    next_offset = offset + len(items) if len(items) == page_size else None

    # cheap total estimate from rollups (within 5%)
    est = await ch.query_one(
        f"""
        SELECT sumMerge(ids_ips_events) AS c
        FROM threatflow.{tf.rollup_table}
        WHERE window_start >= {{since:DateTime64(3,'UTC')}}
          AND window_start <  {{until:DateTime64(3,'UTC')}}
        """,
        {"since": tf.since, "until": tf.until},
    )
    total_est = int((est or {}).get("c") or 0)
    return EventsPage(timeframe=tf.timeframe, items=items, next_offset=next_offset, total_estimate=total_est)


@router.get("/threats.csv")
async def export_threats_csv(
    timeframe: str = Query(default="24h"),
    branch_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    signature: str | None = Query(default=None),
    source_ip: str | None = Query(default=None),
    destination_ip: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=100000),
    _user: User = Depends(get_current_user),
):
    """Export filtered threats to CSV. Capped at 100k rows for one request."""
    tf = parse(timeframe)
    where = ["event_time >= {since:DateTime64(3,'UTC')}", "event_time < {until:DateTime64(3,'UTC')}"]
    params = {"since": tf.since, "until": tf.until, "limit": limit}
    if branch_id:      where.append("branch_id = {bid:UUID}");           params["bid"] = branch_id
    if severity:       where.append("severity = {sev:String}");          params["sev"] = severity
    if signature:      where.append("positionCaseInsensitive(signature, {sig:String}) > 0"); params["sig"] = signature
    if source_ip:      where.append("source_ip = {sip:String}");         params["sip"] = source_ip
    if destination_ip: where.append("destination_ip = {dip:String}");    params["dip"] = destination_ip
    if action:         where.append("action = {act:String}");            params["act"] = action

    sql = f"""
        SELECT event_time, branch_code, branch_name, action, severity, risk,
               signature, threat_category, source_ip, source_hostname,
               destination_ip, destination_hostname, destination_country,
               protocol, policy_type, policy_name
        FROM threatflow.raw_threat_events
        WHERE {" AND ".join(where)}
        ORDER BY event_time DESC
        LIMIT {{limit:UInt32}}
    """
    rows = await ch.query(sql, params)

    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow({k: ("" if v is None else v) for k, v in r.items()})
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=threats-{tf.timeframe}.csv"},
    )


@router.get("/threats/{event_id}", response_model=ThreatEvent)
async def get_threat(event_id: str, _user: User = Depends(get_current_user)):
    sql = """
        SELECT
            toString(event_id) AS event_id, event_hash,
            branch_code, branch_name, event_time,
            action, risk, severity, policy_type, policy_name,
            source_ip, source_hostname,
            destination_ip, destination_port, destination_hostname, destination_country,
            protocol, signature, threat_category, client_ip,
            0 AS bytes_up, 0 AS bytes_down,
            '' AS application, '' AS application_category
        FROM threatflow.raw_threat_events
        WHERE toString(event_id) = {eid:String}
        ORDER BY ingest_time DESC
        LIMIT 1
    """
    row = await ch.query_one(sql, {"eid": event_id})
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="threat_not_found")
    return ThreatEvent(**row)


@router.get("/blocked", response_model=EventsPage)
async def list_blocked(
    timeframe: str = Query(default="24h"),
    branch_id: UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    _user: User = Depends(get_current_user),
):
    tf = parse(timeframe)
    where = [
        "event_time >= {since:DateTime64(3,'UTC')}",
        "event_time < {until:DateTime64(3,'UTC')}",
        "action = 'block'",
    ]
    params: dict[str, Any] = {"since": tf.since, "until": tf.until}
    if branch_id:
        where.append("branch_id = {bid:UUID}"); params["bid"] = branch_id
    offset = (page - 1) * page_size
    params["limit"] = page_size
    params["offset"] = offset

    sql = f"""
        SELECT
            toString(event_id) AS event_id, event_hash,
            branch_code, branch_name, event_time,
            action, risk, severity, policy_type, policy_name,
            source_ip, source_hostname,
            destination_ip, destination_port, destination_hostname, destination_country,
            protocol, application, application_category,
            bytes_up, bytes_down
        FROM threatflow.raw_flow_events
        WHERE {" AND ".join(where)}
        ORDER BY event_time DESC
        LIMIT {{limit:UInt32}} OFFSET {{offset:UInt32}}
    """
    rows = await ch.query(sql, params)
    items = [FlowEvent(**r) for r in rows]
    next_offset = offset + len(items) if len(items) == page_size else None

    est = await ch.query_one(
        f"""
        SELECT sumMerge(blocked_flows) AS c
        FROM threatflow.{tf.rollup_table}
        WHERE window_start >= {{since:DateTime64(3,'UTC')}}
          AND window_start <  {{until:DateTime64(3,'UTC')}}
        """,
        {"since": tf.since, "until": tf.until},
    )
    total_est = int((est or {}).get("c") or 0)
    return EventsPage(timeframe=tf.timeframe, items=items, next_offset=next_offset, total_estimate=total_est)
