"""Stable event-hash regression — same event must produce the same hash; any
field change must produce a different hash."""
import sys, pathlib

# Allow `import collector.app.dedupe` from the backend test runner
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "collector"))

from app.dedupe import event_hash  # noqa: E402  (collector/app/dedupe.py)


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
