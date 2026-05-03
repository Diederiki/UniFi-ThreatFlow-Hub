"""Stable event hash per blueprint § Deduplication."""
from __future__ import annotations

import hashlib
from typing import Any


def event_hash(event: dict[str, Any]) -> str:
    parts = [
        str(event.get("branch_id", "")),
        str(event.get("event_time", "")),
        str(event.get("source_ip", "")),
        str(event.get("source_port", "")),
        str(event.get("destination_ip", "")),
        str(event.get("destination_port", "")),
        str(event.get("protocol", "")),
        str(event.get("action", "")),
        str(event.get("policy_type", "")),
        str(event.get("policy_name", "")),
        str(event.get("signature", "")),
        str(event.get("risk", "") or event.get("severity", "")),
        str(event.get("bytes_up", 0)),
        str(event.get("bytes_down", 0)),
        str(event.get("duration_ms", 0)),
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8"), usedforsecurity=False).hexdigest()
