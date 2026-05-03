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


# (rollup_state_column, raw_event_column)
_KIND = {
    "destinations": ("top_destinations", "destination_ip"),
    "domains":      ("top_domains",      "destination_hostname"),
    "applications": ("top_apps",         "application"),
    "categories":   ("top_categories",   "application_category"),
    "clients":      ("top_clients",      "source_ip"),
    "countries":    ("top_countries",    "destination_country"),
}


async def _topk_with_counts(kind: str, timeframe: str, limit: int) -> list[TopItem]:
    """Pick candidate labels via topKMerge over the rollup, then count
    occurrences in raw_flow_events. The rollup's topKState column has a
    different name than the raw column it tracks, so we pass both."""
    rollup_col, raw_col = _KIND[kind]
    tf = parse(timeframe)
    candidates_row = await ch.query_one(
        f"""
        SELECT topKMerge(20)({rollup_col}) AS k
        FROM threatflow.{tf.rollup_table}
        WHERE window_start >= {{since:DateTime64(3,'UTC')}}
          AND window_start <  {{until:DateTime64(3,'UTC')}}
        """,
        {"since": tf.since, "until": tf.until},
    )
    candidates = list((candidates_row or {}).get("k") or [])
    if not candidates:
        return []
    rows = await ch.query(
        f"""
        SELECT {raw_col} AS label, count() AS c
        FROM threatflow.raw_flow_events
        WHERE event_time >= {{since:DateTime64(3,'UTC')}}
          AND event_time <  {{until:DateTime64(3,'UTC')}}
          AND {raw_col} IN ({{candidates:Array(String)}})
        GROUP BY label
        ORDER BY c DESC
        LIMIT {{limit:UInt32}}
        """,
        {"since": tf.since, "until": tf.until, "candidates": candidates, "limit": limit},
    )
    return [TopItem(label=str(r["label"]), value=int(r["c"])) for r in rows]


@router.get("/destinations", response_model=TopResponse)
async def top_destinations(timeframe: str = Query(default="24h"), limit: int = Query(default=20, ge=1, le=100), _user: User = Depends(get_current_user)):
    return TopResponse(timeframe=parse(timeframe).timeframe, items=await _topk_with_counts("destinations", timeframe, limit))


@router.get("/domains", response_model=TopResponse)
async def top_domains(timeframe: str = Query(default="24h"), limit: int = Query(default=20, ge=1, le=100), _user: User = Depends(get_current_user)):
    return TopResponse(timeframe=parse(timeframe).timeframe, items=await _topk_with_counts("domains", timeframe, limit))


@router.get("/applications", response_model=TopResponse)
async def top_applications(timeframe: str = Query(default="24h"), limit: int = Query(default=20, ge=1, le=100), _user: User = Depends(get_current_user)):
    return TopResponse(timeframe=parse(timeframe).timeframe, items=await _topk_with_counts("applications", timeframe, limit))


@router.get("/categories", response_model=TopResponse)
async def top_categories(timeframe: str = Query(default="24h"), limit: int = Query(default=20, ge=1, le=100), _user: User = Depends(get_current_user)):
    return TopResponse(timeframe=parse(timeframe).timeframe, items=await _topk_with_counts("categories", timeframe, limit))


@router.get("/clients", response_model=TopResponse)
async def top_clients(timeframe: str = Query(default="24h"), limit: int = Query(default=20, ge=1, le=100), _user: User = Depends(get_current_user)):
    return TopResponse(timeframe=parse(timeframe).timeframe, items=await _topk_with_counts("clients", timeframe, limit))


@router.get("/countries", response_model=TopResponse)
async def top_countries(timeframe: str = Query(default="24h"), limit: int = Query(default=20, ge=1, le=100), _user: User = Depends(get_current_user)):
    return TopResponse(timeframe=parse(timeframe).timeframe, items=await _topk_with_counts("countries", timeframe, limit))


@router.get("/signatures", response_model=TopResponse)
async def top_signatures(
    timeframe: str = Query(default="24h"),
    limit: int = Query(default=20, ge=1, le=100),
    branch_id: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
):
    """Top IDS/IPS signatures from raw_threat_events. Counted directly because
    rollups don't store signature topK."""
    tf = parse(timeframe)
    bf = " AND branch_id = {bid:UUID}" if branch_id else ""
    bp: dict = {"bid": branch_id} if branch_id else {}
    rows = await ch.query(
        f"""
        SELECT signature AS label, count() AS c
        FROM threatflow.raw_threat_events
        WHERE event_time >= {{since:DateTime64(3,'UTC')}}
          AND event_time <  {{until:DateTime64(3,'UTC')}}{bf}
          AND signature != ''
        GROUP BY label
        ORDER BY c DESC
        LIMIT {{limit:UInt32}}
        """,
        {"since": tf.since, "until": tf.until, "limit": limit, **bp},
    )
    return TopResponse(timeframe=tf.timeframe, items=[TopItem(label=str(r["label"]), value=int(r["c"])) for r in rows])
