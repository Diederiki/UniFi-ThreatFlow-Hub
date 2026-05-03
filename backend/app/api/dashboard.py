"""Top-level dashboard surface — overview KPIs + traffic/threat trend +
suspicious branch ranking. Reads only from rollups so even 1y is fast."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.clickhouse import client as ch
from app.db.session import get_db
from app.models.branch import Branch, CollectorStatus
from app.models.user import User
from app.schemas.dashboard import (
    BranchHeatRow,
    OverviewKpis,
    OverviewResponse,
    TrendPoint,
    TrendResponse,
    TrendSeries,
)
from app.utils.timeframe import parse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=OverviewResponse)
async def overview(
    timeframe: str = Query(default="24h"),
    branch_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    tf = parse(timeframe)
    branch_filter = " AND branch_id = {bid:UUID}" if branch_id else ""
    branch_params: dict = {"bid": branch_id} if branch_id else {}

    # Cheap counts from PG
    total_branches = (await db.execute(select(func.count(Branch.id)))).scalar_one()
    online = (
        await db.execute(
            select(func.count())
            .select_from(CollectorStatus)
            .join(Branch, Branch.id == CollectorStatus.branch_id)
            .where(Branch.enabled.is_(True))
            .where(CollectorStatus.status == "ok")
        )
    ).scalar_one()

    # KPI aggregates from CH
    kpi_row = await ch.query_one(
        f"""
        SELECT
            sumMerge(total_flows)        AS flows,
            sumMerge(allowed_flows)      AS allowed,
            sumMerge(blocked_flows)      AS blocked,
            sumMerge(ids_ips_events)     AS ids,
            sumMerge(high_risk_events)   AS high_r,
            sumMerge(medium_risk_events) AS med_r,
            sumMerge(low_risk_events)    AS low_r,
            uniqMerge(unique_clients)    AS uniq_c
        FROM threatflow.{tf.rollup_table}
        WHERE window_start >= {{since:DateTime64(3,'UTC')}}
          AND window_start <  {{until:DateTime64(3,'UTC')}}{branch_filter}
        """,
        {"since": tf.since, "until": tf.until, **branch_params},
    )
    kpis = OverviewKpis(
        total_branches=int(total_branches),
        online_collectors=int(online),
        total_flows=int((kpi_row or {}).get("flows") or 0),
        allowed_flows=int((kpi_row or {}).get("allowed") or 0),
        blocked_flows=int((kpi_row or {}).get("blocked") or 0),
        ids_ips_events=int((kpi_row or {}).get("ids") or 0),
        high_risk_events=int((kpi_row or {}).get("high_r") or 0),
        medium_risk_events=int((kpi_row or {}).get("med_r") or 0),
        low_risk_events=int((kpi_row or {}).get("low_r") or 0),
        unique_clients=int((kpi_row or {}).get("uniq_c") or 0),
    )

    # Branch heat — per-branch rollup with a quick suspicion score
    rows = await ch.query(
        f"""
        SELECT
            branch_id, branch_code, branch_name,
            sumMerge(total_flows)      AS flows,
            sumMerge(blocked_flows)    AS blocked,
            sumMerge(ids_ips_events)   AS ids,
            sumMerge(high_risk_events) AS high_r
        FROM threatflow.{tf.rollup_table}
        WHERE window_start >= {{since:DateTime64(3,'UTC')}}
          AND window_start <  {{until:DateTime64(3,'UTC')}}{branch_filter}
        GROUP BY branch_id, branch_code, branch_name
        ORDER BY ids DESC, blocked DESC
        LIMIT 50
        """,
        {"since": tf.since, "until": tf.until, **branch_params},
    )
    branch_heat = [
        BranchHeatRow(
            branch_id=r["branch_id"],
            branch_code=r["branch_code"],
            branch_name=r["branch_name"],
            flows=int(r["flows"]),
            blocked=int(r["blocked"]),
            ids_ips=int(r["ids"]),
            high_risk=int(r["high_r"]),
            suspicion_score=float(int(r["high_r"]) * 10 + int(r["ids"]) * 4 + int(r["blocked"]) * 0.5),
        )
        for r in rows
    ]

    if branch_heat:
        kpis.top_suspicious_branch = max(branch_heat, key=lambda b: b.suspicion_score).branch_code

    # Top suspicious client (cheap topK over rollup)
    top_client = await ch.query_one(
        f"""
        SELECT arraySlice(topKMerge(20)(top_clients), 1, 1)[1] AS top_c
        FROM threatflow.{tf.rollup_table}
        WHERE window_start >= {{since:DateTime64(3,'UTC')}}
          AND window_start <  {{until:DateTime64(3,'UTC')}}
        """,
        {"since": tf.since, "until": tf.until},
    )
    if top_client and top_client.get("top_c"):
        kpis.top_suspicious_client = str(top_client["top_c"])

    return OverviewResponse(timeframe=tf.timeframe, kpis=kpis, branch_heat=branch_heat)


@router.get("/traffic-trend", response_model=TrendResponse)
async def traffic_trend(
    timeframe: str = Query(default="24h"),
    branch_id: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
):
    tf = parse(timeframe)
    bf = " AND branch_id = {bid:UUID}" if branch_id else ""
    bp: dict = {"bid": branch_id} if branch_id else {}
    rows = await ch.query(
        f"""
        SELECT
            toStartOfInterval(window_start, INTERVAL {tf.bucket_seconds} SECOND) AS t,
            sumMerge(allowed_flows) AS allowed,
            sumMerge(blocked_flows) AS blocked
        FROM threatflow.{tf.rollup_table}
        WHERE window_start >= {{since:DateTime64(3,'UTC')}}
          AND window_start <  {{until:DateTime64(3,'UTC')}}{bf}
        GROUP BY t
        ORDER BY t
        """,
        {"since": tf.since, "until": tf.until, **bp},
    )
    return TrendResponse(
        timeframe=tf.timeframe,
        bucket_label=tf.bucket_label,
        series=[
            TrendSeries(name="allowed", points=[TrendPoint(t=r["t"], value=int(r["allowed"])) for r in rows]),
            TrendSeries(name="blocked", points=[TrendPoint(t=r["t"], value=int(r["blocked"])) for r in rows]),
        ],
    )


@router.get("/threat-trend", response_model=TrendResponse)
async def threat_trend(
    timeframe: str = Query(default="24h"),
    branch_id: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
):
    tf = parse(timeframe)
    bf = " AND branch_id = {bid:UUID}" if branch_id else ""
    bp: dict = {"bid": branch_id} if branch_id else {}
    rows = await ch.query(
        f"""
        SELECT
            toStartOfInterval(window_start, INTERVAL {tf.bucket_seconds} SECOND) AS t,
            sumMerge(ids_ips_events)     AS ids,
            sumMerge(high_risk_events)   AS high_r,
            sumMerge(medium_risk_events) AS med_r
        FROM threatflow.{tf.rollup_table}
        WHERE window_start >= {{since:DateTime64(3,'UTC')}}
          AND window_start <  {{until:DateTime64(3,'UTC')}}{bf}
        GROUP BY t
        ORDER BY t
        """,
        {"since": tf.since, "until": tf.until, **bp},
    )
    return TrendResponse(
        timeframe=tf.timeframe,
        bucket_label=tf.bucket_label,
        series=[
            TrendSeries(name="ids_ips",     points=[TrendPoint(t=r["t"], value=int(r["ids"]))    for r in rows]),
            TrendSeries(name="high_risk",   points=[TrendPoint(t=r["t"], value=int(r["high_r"])) for r in rows]),
            TrendSeries(name="medium_risk", points=[TrendPoint(t=r["t"], value=int(r["med_r"]))  for r in rows]),
        ],
    )
