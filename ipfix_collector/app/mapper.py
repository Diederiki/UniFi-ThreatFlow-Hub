"""Translate parsed flow records into `raw_flow_events` rows.

Each parsed record is a dict keyed by IPFIX information element id
(see parser.py). We pick the standard fields we care about and produce
a row matching the existing schema.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.parser import (
    IE_destinationIPv4Address, IE_destinationMacAddress,
    IE_destinationTransportPort, IE_egressInterface, IE_flowEndMilliseconds,
    IE_flowEndSeconds, IE_flowStartMilliseconds, IE_flowStartSeconds,
    IE_ingressInterface, IE_octetDeltaCount, IE_octetTotalCount,
    IE_packetDeltaCount, IE_packetTotalCount, IE_postOctetDeltaCount,
    IE_postPacketDeltaCount, IE_protocolIdentifier, IE_sourceIPv4Address,
    IE_sourceMacAddress, IE_sourceTransportPort, IE_tcpControlBits,
    IE_flowDirection,
)

PROTO_NAMES = {1: "icmp", 2: "igmp", 6: "tcp", 17: "udp", 47: "gre", 50: "esp", 58: "icmp6"}


def _event_time(rec: dict[int, Any]) -> datetime:
    end_ms = rec.get(IE_flowEndMilliseconds)
    if end_ms:
        return datetime.fromtimestamp(end_ms / 1000.0, tz=timezone.utc)
    end_s = rec.get(IE_flowEndSeconds)
    if end_s:
        return datetime.fromtimestamp(end_s, tz=timezone.utc)
    et = rec.get("_export_time")
    if et:
        return datetime.fromtimestamp(et, tz=timezone.utc)
    return datetime.now(timezone.utc)


def _duration_ms(rec: dict[int, Any]) -> int:
    s_ms = rec.get(IE_flowStartMilliseconds)
    e_ms = rec.get(IE_flowEndMilliseconds)
    if s_ms and e_ms and e_ms >= s_ms:
        return int(e_ms - s_ms)
    s_s = rec.get(IE_flowStartSeconds)
    e_s = rec.get(IE_flowEndSeconds)
    if s_s and e_s and e_s >= s_s:
        return int((e_s - s_s) * 1000)
    return 0


def _hash(branch_id: str, rec: dict[int, Any]) -> str:
    """Stable per-flow hash so a re-emitted flow record (e.g. due to
    template re-send + replay) deduplicates naturally via
    ReplacingMergeTree on event_hash."""
    parts = [
        branch_id,
        str(rec.get(IE_sourceIPv4Address, "")),
        str(rec.get(IE_sourceTransportPort, "")),
        str(rec.get(IE_destinationIPv4Address, "")),
        str(rec.get(IE_destinationTransportPort, "")),
        str(rec.get(IE_protocolIdentifier, "")),
        str(rec.get(IE_flowStartMilliseconds, rec.get(IE_flowStartSeconds, ""))),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def map_record(
    rec: dict[int, Any], *,
    branch_id: str, branch_name: str, branch_code: str,
    collector_version: str = "ipfix/0.1",
) -> dict[str, Any]:
    proto = int(rec.get(IE_protocolIdentifier, 0))
    bytes_total = int(rec.get(IE_octetDeltaCount, rec.get(IE_octetTotalCount, 0)))
    pkts_total  = int(rec.get(IE_packetDeltaCount, rec.get(IE_packetTotalCount, 0)))
    # If the exporter sends both delta and post-delta counts we treat the
    # post-* values as the reverse direction; otherwise we lump everything
    # into the "down" bucket (toward source).
    bytes_post = int(rec.get(IE_postOctetDeltaCount, 0))
    pkts_post  = int(rec.get(IE_postPacketDeltaCount, 0))
    if bytes_post:
        bytes_down = bytes_total
        bytes_up   = bytes_post
        pkts_down  = pkts_total
        pkts_up    = pkts_post
    else:
        bytes_down = bytes_total
        bytes_up   = 0
        pkts_down  = pkts_total
        pkts_up    = 0

    direction = "outbound"
    fd = rec.get(IE_flowDirection)
    if fd is not None:
        direction = "outbound" if fd == 0 else "inbound"

    # Compact raw_json for forensics, not the entire IE dict.
    keep_raw = {
        "in_iface": rec.get(IE_ingressInterface),
        "out_iface": rec.get(IE_egressInterface),
        "tcp_flags": rec.get(IE_tcpControlBits),
        "src_mac": rec.get(IE_sourceMacAddress),
        "dst_mac": rec.get(IE_destinationMacAddress),
    }
    raw_json = json.dumps({k: v for k, v in keep_raw.items() if v not in (None, "")})

    return {
        "event_hash":           _hash(branch_id, rec),
        "branch_id":            branch_id,
        "branch_name":          branch_name,
        "branch_code":          branch_code,
        "event_time":           _event_time(rec),
        "action":               "allow",      # IPFIX exports allowed flows; blocks come via syslog later
        "risk":                 "low",
        "severity":             "low",
        "policy_type":          "flow",
        "policy_name":          "",
        "source_ip":            str(rec.get(IE_sourceIPv4Address, "")),
        "source_port":          int(rec.get(IE_sourceTransportPort, 0)),
        "source_mac":           str(rec.get(IE_sourceMacAddress, "")),
        "source_hostname":      "",
        "source_vlan":          "",
        "destination_ip":       str(rec.get(IE_destinationIPv4Address, "")),
        "destination_port":     int(rec.get(IE_destinationTransportPort, 0)),
        "destination_hostname": "",
        "destination_country":  "",
        "protocol":             PROTO_NAMES.get(proto, str(proto)),
        "application":          "",
        "application_category": "",
        "bytes_up":             bytes_up,
        "bytes_down":           bytes_down,
        "packets_up":           pkts_up,
        "packets_down":         pkts_down,
        "duration_ms":          _duration_ms(rec),
        "direction":            direction,
        "raw_json":             raw_json,
        "collector_version":    collector_version,
    }
