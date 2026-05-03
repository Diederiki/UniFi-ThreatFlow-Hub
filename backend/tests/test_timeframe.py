"""Timeframe parser + rollup picker."""
from datetime import timedelta

import pytest

from app.utils.timeframe import ALLOWED, parse


@pytest.mark.parametrize("tf, expected_table", [
    ("5m",  "rollup_1m"),
    ("15m", "rollup_1m"),
    ("1h",  "rollup_5m"),
    ("4h",  "rollup_15m"),
    ("12h", "rollup_15m"),
    ("24h", "rollup_1h"),
    ("3d",  "rollup_1h"),
    ("7d",  "rollup_1h"),
    ("14d", "rollup_1d"),
    ("1m",  "rollup_1d"),
    ("6m",  "rollup_1d"),
    ("1y",  "rollup_1d"),
])
def test_parse_picks_correct_rollup(tf, expected_table):
    w = parse(tf)
    assert w.timeframe == tf
    assert w.rollup_table == expected_table


def test_parse_falls_back_to_24h_for_garbage():
    assert parse("nonsense").timeframe == "24h"
    assert parse(None).timeframe == "24h"
    assert parse("").timeframe == "24h"


def test_window_is_in_the_past():
    w = parse("1h")
    assert (w.until - w.since) == timedelta(hours=1)


def test_long_timeframes_never_use_raw():
    """Per blueprint § Performance Rules — never query raw for ≥6m."""
    for tf in ("6m", "1y"):
        w = parse(tf)
        assert w.rollup_table == "rollup_1d"


def test_all_listed_timeframes_have_a_plan():
    for tf in ALLOWED:
        w = parse(tf)
        assert w.rollup_table.startswith("rollup_")
        assert w.bucket_seconds >= 60
