"""Pure mapper: UniFi controller event JSON -> raw_*_events rows.

Input: a decoded message dict from the cloud-proxy WebRTC data channel — i.e.
the body of the `wss/s/<site>/events` channel after zlib chunks are reassembled
and JSON-parsed. Both single-data shape and the standard meta+data envelope
are accepted.

Output: two lists, (flow_rows, threat_rows), suitable for the existing
`raw_flow_events` / `raw_threat_events` ClickHouse schema.

Deliberate non-goals
--------------------
This mapper does NOT enrich with MITRE/CVE — that's the collector's
threat_enricher's job, run downstream via the existing batch_writer.

Currently understood event keys
------------------------------
- EVT_LU_*  / EVT_WU_*       : client connect/disconnect.   -> flow rows, action='allow'
- EVT_FW_*  / EVT_*_Block*   : firewall block.              -> flow rows, action='block'
- EVT_IDS_*, EVT_IPS_*       : IDS/IPS detection.           -> threat rows
- EVT_GW_DPI_* / EVT_GW_TM_* : threat management.           -> threat rows
- Anything else              : skipped (silent, intentional)

Event shape from UniFi (observed):
    {"user": "<mac>", "hostname": "...", "network": "<vlan name>",
     "duration": 17796, "bytes": 0, "key": "EVT_LU_Disconnected",
     "subsystem": "lan", "is_negative": false, "site_id": "...",
     "time": 1777891300000, "datetime": "2026-05-04T10:41:40Z",
     "msg": "User[mac] disconnected from \"vlan\" (...)"}
For IDS/IPS the payload also typically carries: src_ip, dst_ip, src_port,
dst_port, signature, category, in_iface, out_iface, app_proto.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

# Suricata signatures embedded in UniFi IDS events sometimes include
# "[N:SID:R]" prefix; strip that for cleaner display.
_SIG_PREFIX_RE = re.compile(r"^\s*\[\s*\d+\s*:\s*\d+\s*:\s*\d+\s*\]\s*")


def _parse_event_time(ev: dict[str, Any]) -> datetime:
    t = ev.get("time")
    if isinstance(t, (int, float)):
        # UniFi sends ms epoch
        return datetime.fromtimestamp(t / 1000.0, tz=timezone.utc)
    dt = ev.get("datetime")
    if isinstance(dt, str):
        try:
            return datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _hash_event(ev: dict[str, Any]) -> str:
    """Stable per-event hash so re-ingestion deduplicates naturally
    (raw_*_events use ReplacingMergeTree on event_hash)."""
    parts = [
        ev.get("key", ""),
        ev.get("user", ev.get("client_mac", "")),
        ev.get("src_ip", ev.get("source_ip", "")),
        ev.get("dst_ip", ev.get("destination_ip", "")),
        str(ev.get("time", "")),
        ev.get("signature", ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _severity_from_key(key: str) -> tuple[str, str]:
    """Returns (severity, risk) tuple."""
    k = key.upper()
    if any(w in k for w in ("CRITICAL", "EMERGENCY", "MALWARE", "EXPLOIT")):
        return "critical", "high"
    if any(w in k for w in ("IDS", "IPS", "BLOCK", "DENY", "INTRUSION")):
        return "high", "high"
    if any(w in k for w in ("ANOMAL", "SUSPICIOUS")):
        return "medium", "medium"
    return "low", "low"


def _normalize_signature(ev: dict[str, Any]) -> str:
    """Pick the best candidate string to identify the event."""
    sig = ev.get("signature") or ev.get("rule") or ev.get("msg") or ev.get("key") or ""
    sig = _SIG_PREFIX_RE.sub("", str(sig))
    return sig.strip()[:512]


def map_event(
    ev: dict[str, Any],
    *,
    branch_id: str,
    branch_name: str,
    branch_code: str,
    collector_version: str = "cloudproxy/0.1",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert one UniFi event to (flow_rows, threat_rows). Both may be empty."""
    key = str(ev.get("key", ""))
    if not key.startswith("EVT_"):
        return [], []

    et = _parse_event_time(ev)
    base = {
        "branch_id":         branch_id,
        "branch_name":       branch_name,
        "branch_code":       branch_code,
        "event_time":        et,
        "raw_json":          json.dumps(ev, default=str)[:8192],
        "collector_version": collector_version,
    }
    src_ip = ev.get("src_ip") or ev.get("source_ip") or ev.get("client_ip") or ""
    dst_ip = ev.get("dst_ip") or ev.get("destination_ip") or ""
    src_mac = ev.get("user") or ev.get("client_mac") or ""
    dst_mac = ev.get("dst_mac") or ""
    hostname = ev.get("hostname") or ""

    is_threat = (
        "IDS" in key or "IPS" in key or
        key.startswith(("EVT_GW_DPI", "EVT_GW_TM"))
    )
    is_firewall = key.startswith("EVT_FW_")
    is_block = (
        "BLOCK" in key.upper() or "DENY" in key.upper() or
        (is_firewall and "Allow" not in key)
    )
    # Skip everything that isn't a security-relevant event. LU/WU/AD/AP/SW
    # device events fill `raw_*_events` with mostly-empty rows that pollute
    # the dashboards rather than illuminate them.
    if not (is_threat or is_firewall):
        return [], []

    if is_threat:
        sev, risk = _severity_from_key(key)
        threat = {
            **base,
            "event_hash":           _hash_event(ev),
            "action":               "block" if is_block else "detect",
            "severity":             sev,
            "risk":                 risk,
            "signature":            _normalize_signature(ev),
            "threat_category":      ev.get("category") or ev.get("subsystem") or "ids_ips",
            "policy_type":          "ids_ips",
            "policy_name":          ev.get("rule") or "",
            "source_ip":            src_ip,
            "source_port":          int(ev.get("src_port") or ev.get("source_port") or 0),
            "source_mac":           src_mac,
            "source_hostname":      hostname,
            "destination_ip":       dst_ip,
            "destination_port":     int(ev.get("dst_port") or ev.get("destination_port") or 0),
            "destination_hostname": ev.get("dst_hostname") or "",
            "destination_country":  (ev.get("dst_country") or "").upper()[:2],
            "protocol":             (ev.get("proto") or ev.get("app_proto") or "").lower(),
            "client_ip":            src_ip,
            "client_mac":           src_mac,
            "client_hostname":      hostname,
        }
        return [], [threat]

    # Flow row (allow / block)
    action = "block" if is_block else "allow"
    flow = {
        **base,
        "event_hash":           _hash_event(ev),
        "action":               action,
        "risk":                 "high" if is_block else "low",
        "severity":             "high" if is_block else "low",
        "policy_type":          "firewall" if key.startswith("EVT_FW_") else "client",
        "policy_name":          ev.get("rule") or "",
        "source_ip":            src_ip,
        "source_port":          int(ev.get("src_port") or 0),
        "source_mac":           src_mac,
        "source_hostname":      hostname,
        "source_vlan":          ev.get("network") or "",
        "destination_ip":       dst_ip,
        "destination_port":     int(ev.get("dst_port") or 0),
        "destination_hostname": ev.get("dst_hostname") or "",
        "destination_country":  (ev.get("dst_country") or "").upper()[:2],
        "protocol":             (ev.get("proto") or "").lower(),
        "application":          ev.get("app") or "",
        "application_category": ev.get("app_cat") or "",
        "bytes_up":             int(ev.get("bytes_tx") or ev.get("bytes_up") or 0),
        "bytes_down":           int(ev.get("bytes_rx") or ev.get("bytes_down") or ev.get("bytes") or 0),
        "packets_up":           int(ev.get("pkts_tx") or 0),
        "packets_down":         int(ev.get("pkts_rx") or 0),
        "duration_ms":          int((ev.get("duration") or 0) * 1000),
        "direction":            "outbound",
    }
    return [flow], []


def map_events(
    events: list[dict[str, Any]], **branch_kwargs: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    flows, threats = [], []
    for ev in events:
        f, t = map_event(ev, **branch_kwargs)
        flows.extend(f)
        threats.extend(t)
    return flows, threats
