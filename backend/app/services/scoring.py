"""Suspicion scoring engine.

Default weights live in code; admins can override via PUT /api/scoring (stored
in `app_settings` under key `scoring_weights`). All dashboard scoring queries
go through `current_weights()` so a tweak instantly affects new computations.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting

SETTING_KEY = "scoring_weights"


@dataclass
class ScoringWeights:
    high_risk_event: float = 10.0
    medium_risk_event: float = 5.0
    low_risk_event: float = 1.0
    blocked_event: float = 4.0
    repeated_client: float = 8.0
    outbound_suspicious: float = 6.0
    malware_botnet: float = 15.0
    large_transfer: float = 5.0
    known_false_positive: float = -3.0


DEFAULT = ScoringWeights()


async def current_weights(db: AsyncSession) -> ScoringWeights:
    row = (await db.execute(select(AppSetting).where(AppSetting.key == SETTING_KEY))).scalar_one_or_none()
    if not row:
        return ScoringWeights()
    data = row.value or {}
    return ScoringWeights(**{**asdict(DEFAULT), **{k: float(v) for k, v in data.items() if k in DEFAULT.__dict__}})


async def set_weights(db: AsyncSession, w: ScoringWeights) -> ScoringWeights:
    payload: dict[str, Any] = asdict(w)
    existing = (await db.execute(select(AppSetting).where(AppSetting.key == SETTING_KEY))).scalar_one_or_none()
    if existing:
        existing.value = payload
    else:
        db.add(AppSetting(key=SETTING_KEY, value=payload))
    await db.commit()
    return w


def branch_score(*, high_risk: int, medium_risk: int, low_risk: int, blocked: int, ids_ips: int, w: ScoringWeights) -> float:
    """Aggregate score from rollup-friendly counters. Repeated-client / large-
    transfer / malware-signature multipliers are folded in at the threat
    enumeration layer (Phase 6.x), not here."""
    return (
        high_risk    * w.high_risk_event
        + medium_risk* w.medium_risk_event
        + low_risk   * w.low_risk_event
        + blocked    * w.blocked_event
        + ids_ips    * w.outbound_suspicious  # ids/ips events default to "outbound suspicious"
    )
