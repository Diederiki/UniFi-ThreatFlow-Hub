"""/api/top/* — top-N tables for the dashboard. All read from the rollup
tables via topKMerge so they're constant-time regardless of timeframe."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import get_current_user
from app.clickhouse import client as ch
from app.models.user import User
from app.schemas.dashboard import TopItem, TopResponse
from app.utils.timeframe import parse

router = APIRouter(prefix="/top", tags=["top"])


async def _topk_with_counts(state_col: str, count_col: str | None, timeframe: str, limit: int) -> list[TopItem]:
    """Return top items with their actual counts from raw events.

    topKState only stores the labels (no counts), so we use the topK output to
    pick the candidate set and then count occurrences over the same window in
    raw_flow_events. Bounded to 20 candidates × `limit` for the count step,
    which stays cheap because we only filter raw events that are in that set.
    """
    tf = parse(timeframe)
    candidates_row = await ch.query_one(
        f"""
        SELECT topKMerge(20)({state_col}) AS k
        FROM threatflow.{tf.rollup_table}
        WHERE window_start >= {{since:DateTime64(3,'UTC')}}
          AND window_start <  {{until:DateTime64(3,'UTC')}}
        """,
        {"since": tf.since, "until": tf.until},
    )
    candidates = list((candidates_row or {}).get("k") or [])
    if not candidates:
        return []
    # Count actual occurrences in raw events (still filtered so it's quick).
    rows = await ch.query(
        f"""
        SELECT {state_col} AS label, count() AS c
        FROM threatflow.raw_flow_events
        WHERE event_time >= {{since:DateTime64(3,'UTC')}}
          AND event_time <  {{until:DateTime64(3,'UTC')}}
          AND {state_col} IN ({{candidates:Array(String)}})
        GROUP BY label
        ORDER BY c DESC
        LIMIT {{limit:UInt32}}
        """,
        {"since": tf.since, "until": tf.until, "candidates": candidates, "limit": limit},
    )
    return [TopItem(label=str(r["label"]), value=int(r["c"])) for r in rows]


@router.get("/destinations", response_model=TopResponse)
async def top_destinations(timeframe: str = Query(default="24h"), limit: int = Query(default=20, ge=1, le=100), _user: User = Depends(get_current_user)):
    items = await _topk_with_counts("destination_ip", None, timeframe, limit)
    return TopResponse(timeframe=parse(timeframe).timeframe, items=items)


@router.get("/domains", response_model=TopResponse)
async def top_domains(timeframe: str = Query(default="24h"), limit: int = Query(default=20, ge=1, le=100), _user: User = Depends(get_current_user)):
    items = await _topk_with_counts("destination_hostname", None, timeframe, limit)
    return TopResponse(timeframe=parse(timeframe).timeframe, items=items)


@router.get("/applications", response_model=TopResponse)
async def top_applications(timeframe: str = Query(default="24h"), limit: int = Query(default=20, ge=1, le=100), _user: User = Depends(get_current_user)):
    items = await _topk_with_counts("application", None, timeframe, limit)
    return TopResponse(timeframe=parse(timeframe).timeframe, items=items)


@router.get("/categories", response_model=TopResponse)
async def top_categories(timeframe: str = Query(default="24h"), limit: int = Query(default=20, ge=1, le=100), _user: User = Depends(get_current_user)):
    items = await _topk_with_counts("application_category", None, timeframe, limit)
    return TopResponse(timeframe=parse(timeframe).timeframe, items=items)


@router.get("/clients", response_model=TopResponse)
async def top_clients(timeframe: str = Query(default="24h"), limit: int = Query(default=20, ge=1, le=100), _user: User = Depends(get_current_user)):
    items = await _topk_with_counts("source_ip", None, timeframe, limit)
    return TopResponse(timeframe=parse(timeframe).timeframe, items=items)


@router.get("/countries", response_model=TopResponse)
async def top_countries(timeframe: str = Query(default="24h"), limit: int = Query(default=20, ge=1, le=100), _user: User = Depends(get_current_user)):
    items = await _topk_with_counts("destination_country", None, timeframe, limit)
    return TopResponse(timeframe=parse(timeframe).timeframe, items=items)
