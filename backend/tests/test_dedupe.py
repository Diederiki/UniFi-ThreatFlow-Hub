"""Stable event-hash regression — same event must produce the same hash; any
field change must produce a different hash.

The collector and the backend share the same hash semantics; the test inlines
the same algorithm so it can run without depending on the collector package
being importable from the backend's test runner.
"""
import hashlib
from typing import Any


def event_hash(event: dict[str, Any]) -> str:
    parts = [
        str(event.get("branch_id", "")), str(event.get("event_time", "")),
        str(event.get("source_ip", "")), str(event.get("source_port", "")),
        str(event.get("destination_ip", "")), str(event.get("destination_port", "")),
        str(event.get("protocol", "")), str(event.get("action", "")),
        str(event.get("policy_type", "")), str(event.get("policy_name", "")),
        str(event.get("signature", "")),
        str(event.get("risk", "") or event.get("severity", "")),
        str(event.get("bytes_up", 0)), str(event.get("bytes_down", 0)),
        str(event.get("duration_ms", 0)),
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8"), usedforsecurity=False).hexdigest()


def _evt(**overrides):
    base = {
        "branch_id": "b1", "event_time": "2026-05-03T15:00:00",
        "source_ip": "10.0.0.1", "source_port": 443,
        "destination_ip": "1.1.1.1", "destination_port": 443,
        "protocol": "tcp", "action": "allow",
        "policy_type": "firewall", "policy_name": "p",
        "signature": "", "risk": "low",
        "bytes_up": 100, "bytes_down": 200, "duration_ms": 1000,
    }
    base.update(overrides)
    return base


def test_same_event_same_hash():
    a = event_hash(_evt())
    b = event_hash(_evt())
    assert a == b
    assert len(a) == 40  # sha1 hex


def test_different_action_different_hash():
    assert event_hash(_evt(action="allow")) != event_hash(_evt(action="block"))


def test_different_destination_different_hash():
    assert event_hash(_evt(destination_ip="1.1.1.1")) != event_hash(_evt(destination_ip="8.8.8.8"))


def test_different_branch_different_hash():
    assert event_hash(_evt(branch_id="b1")) != event_hash(_evt(branch_id="b2"))
