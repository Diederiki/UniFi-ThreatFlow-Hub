"""Parse the global timeframe selector value (5m / 15m / 1h / … / 1y) into:
  - a (since, until) UTC window
  - the best ClickHouse rollup table to read from
  - a "bucket" interval so trend charts get ~20-60 points

Long timeframes (≥6m) MUST use rollup_1d per blueprint § Performance Rules
("never query raw tables for 6m or 1y dashboards").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

Timeframe = Literal[
    "5m", "15m", "1h", "4h", "12h", "24h",
    "3d", "7d", "14d", "1m", "6m", "1y",
]
ALLOWED: tuple[Timeframe, ...] = (
    "5m", "15m", "1h", "4h", "12h", "24h",
    "3d", "7d", "14d", "1m", "6m", "1y",
)


@dataclass
class TimeframeWindow:
    timeframe: Timeframe
    since: datetime
    until: datetime
    rollup_table: str        # e.g. "rollup_1m"
    bucket_seconds: int      # for trend charts (toStartOfInterval)
    bucket_label: str        # human-readable (e.g. "5m")


_DURATION = {
    "5m":  timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h":  timedelta(hours=1),
    "4h":  timedelta(hours=4),
    "12h": timedelta(hours=12),
    "24h": timedelta(hours=24),
    "3d":  timedelta(days=3),
    "7d":  timedelta(days=7),
    "14d": timedelta(days=14),
    "1m":  timedelta(days=30),
    "6m":  timedelta(days=180),
    "1y":  timedelta(days=365),
}

# (rollup_table, bucket_seconds, bucket_label)
# Aim for 12-60 trend points per timeframe and never read raw tables for ≥6m.
_PLAN: dict[str, tuple[str, int, str]] = {
    "5m":  ("rollup_1m",  60,        "1m"),
    "15m": ("rollup_1m",  60,        "1m"),
    "1h":  ("rollup_5m",  300,       "5m"),
    "4h":  ("rollup_15m", 900,       "15m"),
    "12h": ("rollup_15m", 1800,      "30m"),
    "24h": ("rollup_1h",  3600,      "1h"),
    "3d":  ("rollup_1h",  3 * 3600,  "3h"),
    "7d":  ("rollup_1h",  6 * 3600,  "6h"),
    "14d": ("rollup_1d",  86400,     "1d"),
    "1m":  ("rollup_1d",  86400,     "1d"),
    "6m":  ("rollup_1d",  6 * 86400, "6d"),
    "1y":  ("rollup_1d",  7 * 86400, "7d"),
}


def parse(timeframe: str | None) -> TimeframeWindow:
    tf: Timeframe = (timeframe or "24h").lower()  # type: ignore[assignment]
    if tf not in ALLOWED:
        tf = "24h"  # graceful default; never raise on dashboard reads
    until = datetime.now(timezone.utc)
    since = until - _DURATION[tf]
    table, bucket_s, bucket_l = _PLAN[tf]
    return TimeframeWindow(
        timeframe=tf, since=since, until=until,
        rollup_table=table, bucket_seconds=bucket_s, bucket_label=bucket_l,
    )
