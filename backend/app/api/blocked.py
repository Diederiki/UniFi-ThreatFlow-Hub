"""/api/blocked/* — blocked-specific top-N + breakdowns + trend."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import get_current_user
from app.clickhouse import client as ch
from app.models.user import User
from app.schemas.dashboard import TopItem, TopResponse, TrendPoint, TrendResponse, TrendSeries
from app.utils.timeframe import parse

router = APIRouter(prefix="/blocked", tags=["blocked"])


async def _topn(label_col: str, timeframe: str, limit: int) -> list[TopItem]:
    tf = parse(timeframe)
    rows = await ch.query(
        f"""
        SELECT {label_col} AS label, count() AS c
        FROM threatflow.raw_flow_events
        WHERE event_time >= {{since:DateTime64(3,'UTC')}}
          AND event_time <  {{until:DateTime64(3,'UTC')}}
          AND action = 'block'
        GROUP BY label
        ORDER BY c DESC
        LIMIT {{limit:UInt32}}
        """,
        {"since": tf.since, "until": tf.until, "limit": limit},
    )
    return [TopItem(label=str(r["label"]), value=int(r["c"])) for r in rows]


@router.get("/top-destinations", response_model=TopResponse)
async def top_destinations(timeframe: str = Query(default="24h"), limit: int = Query(default=20, ge=1, le=100), _user: User = Depends(get_current_user)):
    return TopResponse(timeframe=parse(timeframe).timeframe, items=await _topn("destination_ip", timeframe, limit))


@router.get("/top-clients", response_model=TopResponse)
async def top_clients(timeframe: str = Query(default="24h"), limit: int = Query(default=20, ge=1, le=100), _user: User = Depends(get_current_user)):
    return TopResponse(timeframe=parse(timeframe).timeframe, items=await _topn("source_ip", timeframe, limit))


@router.get("/top-policies", response_model=TopResponse)
async def top_policies(timeframe: str = Query(default="24h"), limit: int = Query(default=20, ge=1, le=100), _user: User = Depends(get_current_user)):
    return TopResponse(timeframe=parse(timeframe).timeframe, items=await _topn("policy_name", timeframe, limit))


@router.get("/top-countries", response_model=TopResponse)
async def top_countries(timeframe: str = Query(default="24h"), limit: int = Query(default=20, ge=1, le=100), _user: User = Depends(get_current_user)):
    return TopResponse(timeframe=parse(timeframe).timeframe, items=await _topn("destination_country", timeframe, limit))


@router.get("/trend", response_model=TrendResponse)
async def blocked_trend(timeframe: str = Query(default="24h"), _user: User = Depends(get_current_user)):
    tf = parse(timeframe)
    rows = await ch.query(
        f"""
        SELECT
            toStartOfInterval(window_start, INTERVAL {tf.bucket_seconds} SECOND) AS t,
            sumMerge(blocked_flows) AS blocked
        FROM threatflow.{tf.rollup_table}
        WHERE window_start >= {{since:DateTime64(3,'UTC')}}
          AND window_start <  {{until:DateTime64(3,'UTC')}}
        GROUP BY t
        ORDER BY t
        """,
        {"since": tf.since, "until": tf.until},
    )
    return TrendResponse(
        timeframe=tf.timeframe, bucket_label=tf.bucket_label,
        series=[TrendSeries(name="blocked", points=[TrendPoint(t=r["t"], value=int(r["blocked"])) for r in rows])],
    )
