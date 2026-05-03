"""/api/scoring + /api/suspicion endpoints — feed the Suspicion Score page."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.clickhouse import client as ch
from app.db.session import get_db
from app.models.user import User
from app.schemas.dashboard import TrendPoint, TrendResponse, TrendSeries
from app.schemas.scoring import (
    ScoringWeightsModel,
    SuspiciousBranch,
    SuspiciousBranchList,
    SuspiciousClient,
    SuspiciousClientList,
    SuspiciousDestination,
    SuspiciousDestinationList,
)
from app.services.audit import log_action
from app.services.scoring import ScoringWeights, branch_score, current_weights, set_weights
from app.utils.timeframe import parse

router = APIRouter(tags=["suspicion"])


# ---- Scoring weights -------------------------------------------------------

@router.get("/scoring", response_model=ScoringWeightsModel)
async def get_scoring(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    w = await current_weights(db)
    return ScoringWeightsModel(**w.__dict__)


@router.put("/scoring", response_model=ScoringWeightsModel)
async def put_scoring(
    payload: ScoringWeightsModel,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    w = ScoringWeights(**payload.model_dump())
    await set_weights(db, w)
    await log_action(db, actor=user, action="scoring.update", entity_type="settings", metadata=payload.model_dump())
    await db.commit()
    return ScoringWeightsModel(**w.__dict__)


# ---- Top suspicious -------------------------------------------------------

@router.get("/suspicion/branches", response_model=SuspiciousBranchList)
async def top_branches(
    timeframe: str = Query(default="24h"),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    tf = parse(timeframe)
    w = await current_weights(db)
    rows = await ch.query(
        f"""
        SELECT branch_id, branch_code, branch_name,
               sumMerge(total_flows)        AS flows,
               sumMerge(blocked_flows)      AS blocked,
               sumMerge(ids_ips_events)     AS ids,
               sumMerge(high_risk_events)   AS high_r,
               sumMerge(medium_risk_events) AS med_r,
               sumMerge(low_risk_events)    AS low_r
        FROM threatflow.{tf.rollup_table}
        WHERE window_start >= {{since:DateTime64(3,'UTC')}}
          AND window_start <  {{until:DateTime64(3,'UTC')}}
        GROUP BY branch_id, branch_code, branch_name
        """,
        {"since": tf.since, "until": tf.until},
    )
    items = []
    for r in rows:
        score = branch_score(
            high_risk=int(r["high_r"]), medium_risk=int(r["med_r"]), low_risk=int(r["low_r"]),
            blocked=int(r["blocked"]), ids_ips=int(r["ids"]), w=w,
        )
        items.append(SuspiciousBranch(
            branch_id=r["branch_id"], branch_code=r["branch_code"], branch_name=r["branch_name"],
            flows=int(r["flows"]), blocked=int(r["blocked"]), ids_ips=int(r["ids"]),
            high_risk=int(r["high_r"]), medium_risk=int(r["med_r"]), low_risk=int(r["low_r"]),
            score=score,
        ))
    items.sort(key=lambda x: x.score, reverse=True)
    return SuspiciousBranchList(timeframe=tf.timeframe, items=items[:limit])


@router.get("/suspicion/clients", response_model=SuspiciousClientList)
async def top_clients(
    timeframe: str = Query(default="24h"),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    tf = parse(timeframe)
    w = await current_weights(db)
    rows = await ch.query(
        f"""
        SELECT
            source_ip                                          AS client_ip,
            any(branch_code)                                    AS branch_code,
            count()                                             AS flows,
            countIf(action = 'block')                           AS blocked,
            countIf(policy_type IN ('ids','ips','ids_ips'))     AS threats,
            countIf(risk = 'high')                              AS high_r,
            countIf(risk = 'medium')                            AS med_r,
            countIf(risk = 'low')                               AS low_r
        FROM threatflow.raw_flow_events
        WHERE event_time >= {{since:DateTime64(3,'UTC')}}
          AND event_time <  {{until:DateTime64(3,'UTC')}}
        GROUP BY source_ip
        ORDER BY threats DESC, blocked DESC
        LIMIT {{limit:UInt32}}
        """,
        {"since": tf.since, "until": tf.until, "limit": limit * 4},
    )
    items = []
    for r in rows:
        score = (int(r["high_r"]) * w.high_risk_event
                 + int(r["med_r"]) * w.medium_risk_event
                 + int(r["low_r"]) * w.low_risk_event
                 + int(r["blocked"]) * w.blocked_event)
        items.append(SuspiciousClient(
            client_ip=r["client_ip"], branch_code=r["branch_code"],
            flows=int(r["flows"]), blocked=int(r["blocked"]), threats=int(r["threats"]),
            score=score,
        ))
    items.sort(key=lambda x: x.score, reverse=True)
    return SuspiciousClientList(timeframe=tf.timeframe, items=items[:limit])


@router.get("/suspicion/destinations", response_model=SuspiciousDestinationList)
async def top_destinations(
    timeframe: str = Query(default="24h"),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    tf = parse(timeframe)
    w = await current_weights(db)
    rows = await ch.query(
        f"""
        SELECT
            destination_ip,
            any(destination_hostname)                           AS destination_hostname,
            any(destination_country)                            AS destination_country,
            count()                                             AS flows,
            countIf(policy_type IN ('ids','ips','ids_ips'))     AS threats,
            countIf(action = 'block')                           AS blocked,
            countIf(risk = 'high')                              AS high_r,
            countIf(risk = 'medium')                            AS med_r
        FROM threatflow.raw_flow_events
        WHERE event_time >= {{since:DateTime64(3,'UTC')}}
          AND event_time <  {{until:DateTime64(3,'UTC')}}
        GROUP BY destination_ip
        ORDER BY threats DESC, blocked DESC
        LIMIT {{limit:UInt32}}
        """,
        {"since": tf.since, "until": tf.until, "limit": limit * 4},
    )
    items = []
    for r in rows:
        score = (int(r["high_r"]) * w.high_risk_event
                 + int(r["med_r"]) * w.medium_risk_event
                 + int(r["blocked"]) * w.blocked_event
                 + int(r["threats"]) * w.outbound_suspicious)
        items.append(SuspiciousDestination(
            destination_ip=r["destination_ip"],
            destination_hostname=r["destination_hostname"] or None,
            destination_country=r["destination_country"] or None,
            flows=int(r["flows"]), threats=int(r["threats"]),
            score=score,
        ))
    items.sort(key=lambda x: x.score, reverse=True)
    return SuspiciousDestinationList(timeframe=tf.timeframe, items=items[:limit])


@router.get("/suspicion/trend", response_model=TrendResponse)
async def suspicion_trend(
    timeframe: str = Query(default="24h"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """A single 'suspicion' series — sum of weighted counters bucketed by tf."""
    tf = parse(timeframe)
    w = await current_weights(db)
    rows = await ch.query(
        f"""
        SELECT
            toStartOfInterval(window_start, INTERVAL {tf.bucket_seconds} SECOND) AS t,
            sumMerge(high_risk_events)   AS high_r,
            sumMerge(medium_risk_events) AS med_r,
            sumMerge(low_risk_events)    AS low_r,
            sumMerge(blocked_flows)      AS blocked,
            sumMerge(ids_ips_events)     AS ids
        FROM threatflow.{tf.rollup_table}
        WHERE window_start >= {{since:DateTime64(3,'UTC')}}
          AND window_start <  {{until:DateTime64(3,'UTC')}}
        GROUP BY t
        ORDER BY t
        """,
        {"since": tf.since, "until": tf.until},
    )
    points = [
        TrendPoint(
            t=r["t"],
            value=branch_score(
                high_risk=int(r["high_r"]), medium_risk=int(r["med_r"]), low_risk=int(r["low_r"]),
                blocked=int(r["blocked"]), ids_ips=int(r["ids"]), w=w,
            ),
        )
        for r in rows
    ]
    return TrendResponse(
        timeframe=tf.timeframe, bucket_label=tf.bucket_label,
        series=[TrendSeries(name="suspicion", points=points)],
    )
