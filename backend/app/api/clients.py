"""/api/clients — list + per-client drilldown. Reads raw_flow_events with
strict time bounds so it stays cheap."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import get_current_user
from app.clickhouse import client as ch
from app.models.user import User
from app.schemas.dashboard import ClientList, ClientSummary, EventsPage, FlowEvent, ThreatEvent
from app.utils.timeframe import parse

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("", response_model=ClientList)
async def list_clients(
    timeframe: str = Query(default="24h"),
    search: str = Query(default=""),
    branch_id: str | None = Query(default=None),
    min_threats: int = Query(default=0, ge=0),
    min_blocked: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    _user: User = Depends(get_current_user),
):
    tf = parse(timeframe)
    where = [
        "event_time >= {since:DateTime64(3,'UTC')}",
        "event_time < {until:DateTime64(3,'UTC')}",
    ]
    params: dict = {"since": tf.since, "until": tf.until, "limit": limit}
    if search:
        where.append("(positionCaseInsensitive(source_ip, {q:String}) > 0 OR positionCaseInsensitive(source_hostname, {q:String}) > 0)")
        params["q"] = search
    if branch_id:
        where.append("branch_id = {bid:UUID}"); params["bid"] = branch_id
    having = []
    if min_threats > 0:
        having.append("countIf(policy_type IN ('ids','ips','ids_ips')) >= {mt:UInt32}"); params["mt"] = min_threats
    if min_blocked > 0:
        having.append("countIf(action = 'block') >= {mb:UInt32}"); params["mb"] = min_blocked
    having_clause = (" HAVING " + " AND ".join(having)) if having else ""
    sql = f"""
        SELECT
            source_ip                                   AS client_ip,
            any(branch_code)                             AS branch_code,
            count()                                      AS flows,
            countIf(action = 'block')                    AS blocked,
            countIf(policy_type IN ('ids','ips','ids_ips')) AS threats,
            sum(bytes_up)                                AS bytes_up,
            sum(bytes_down)                              AS bytes_down
        FROM threatflow.raw_flow_events
        WHERE {" AND ".join(where)}
        GROUP BY source_ip
        {having_clause}
        ORDER BY flows DESC
        LIMIT {{limit:UInt32}}
    """
    rows = await ch.query(sql, params)
    return ClientList(
        timeframe=tf.timeframe,
        items=[ClientSummary(**r) for r in rows],
    )


@router.get("/{client_ip}", response_model=ClientSummary)
async def client_summary(client_ip: str, timeframe: str = Query(default="24h"), _user: User = Depends(get_current_user)):
    """Per-client summary over the timeframe."""
    tf = parse(timeframe)
    row = await ch.query_one(
        """
        SELECT
            source_ip AS client_ip,
            any(branch_code) AS branch_code,
            count() AS flows,
            countIf(action = 'block') AS blocked,
            countIf(policy_type IN ('ids','ips','ids_ips')) AS threats,
            sum(bytes_up) AS bytes_up,
            sum(bytes_down) AS bytes_down
        FROM threatflow.raw_flow_events
        WHERE event_time >= {since:DateTime64(3,'UTC')}
          AND event_time <  {until:DateTime64(3,'UTC')}
          AND source_ip = {ip:String}
        GROUP BY source_ip
        """,
        {"since": tf.since, "until": tf.until, "ip": client_ip},
    )
    if not row:
        return ClientSummary(client_ip=client_ip, branch_code="", flows=0, blocked=0, threats=0, bytes_up=0, bytes_down=0)
    return ClientSummary(**row)


@router.get("/{client_ip}/flows", response_model=EventsPage)
async def client_flows(
    client_ip: str,
    timeframe: str = Query(default="24h"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    _user: User = Depends(get_current_user),
):
    tf = parse(timeframe)
    offset = (page - 1) * page_size
    sql = """
        SELECT
            toString(event_id) AS event_id, event_hash,
            branch_code, branch_name, event_time,
            action, risk, severity, policy_type, policy_name,
            source_ip, source_hostname,
            destination_ip, destination_port, destination_hostname, destination_country,
            protocol, application, application_category,
            bytes_up, bytes_down
        FROM threatflow.raw_flow_events
        WHERE event_time >= {since:DateTime64(3,'UTC')}
          AND event_time <  {until:DateTime64(3,'UTC')}
          AND source_ip = {ip:String}
        ORDER BY event_time DESC
        LIMIT {limit:UInt32} OFFSET {offset:UInt32}
    """
    rows = await ch.query(sql, {"since": tf.since, "until": tf.until, "ip": client_ip, "limit": page_size, "offset": offset})
    items = [FlowEvent(**r) for r in rows]
    return EventsPage(
        timeframe=tf.timeframe, items=items,
        next_offset=offset + len(items) if len(items) == page_size else None,
        total_estimate=len(items) + offset,
    )


@router.get("/{client_ip}/threats", response_model=EventsPage)
async def client_threats(
    client_ip: str,
    timeframe: str = Query(default="24h"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    _user: User = Depends(get_current_user),
):
    tf = parse(timeframe)
    offset = (page - 1) * page_size
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
        WHERE event_time >= {since:DateTime64(3,'UTC')}
          AND event_time <  {until:DateTime64(3,'UTC')}
          AND (source_ip = {ip:String} OR client_ip = {ip:String})
        ORDER BY event_time DESC
        LIMIT {limit:UInt32} OFFSET {offset:UInt32}
    """
    rows = await ch.query(sql, {"since": tf.since, "until": tf.until, "ip": client_ip, "limit": page_size, "offset": offset})
    items = [ThreatEvent(**r) for r in rows]
    return EventsPage(
        timeframe=tf.timeframe, items=items,
        next_offset=offset + len(items) if len(items) == page_size else None,
        total_estimate=len(items) + offset,
    )
