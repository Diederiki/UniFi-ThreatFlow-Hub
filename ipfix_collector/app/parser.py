"""Minimal NetFlow v9 (RFC 3954) + IPFIX (RFC 7011) parser.

Designed for the UniFi UDM Pro / Pro Max use case. Handles:
  - Both NetFlow v9 and IPFIX in one entry point (per-packet version sniff).
  - Per-(exporter, domain, template_id) template registry; data records
    are deferred and dropped if the template hasn't arrived yet.
  - Standard information elements that map directly onto our
    `raw_flow_events` schema. Vendor-specific (enterprise) IEs are read
    but their values are surfaced as raw bytes in the record dict — the
    mapper layer decides what to do with them.

We deliberately don't depend on `pynetflow` / `netflow` packages — both
are either unmaintained or carry a lot of cruft we don't need. The
parser is ~250 lines and easy to audit.
"""
from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("ipfix.parser")

# ----------------------------- Protocol constants ---------------------------

NETFLOW_V9 = 9
IPFIX = 10

# Set IDs that aren't data records.
SET_ID_TEMPLATE_V9 = 0
SET_ID_OPTIONS_TEMPLATE_V9 = 1
SET_ID_TEMPLATE_IPFIX = 2
SET_ID_OPTIONS_TEMPLATE_IPFIX = 3

# IANA-assigned IPFIX information element IDs we actually use.
IE_octetDeltaCount       = 1
IE_packetDeltaCount      = 2
IE_protocolIdentifier    = 4
IE_ipClassOfService      = 5
IE_tcpControlBits        = 6
IE_sourceTransportPort   = 7
IE_sourceIPv4Address     = 8
IE_ingressInterface      = 10
IE_destinationTransportPort = 11
IE_destinationIPv4Address   = 12
IE_egressInterface       = 14
IE_postOctetDeltaCount   = 23
IE_postPacketDeltaCount  = 24
IE_sourceMacAddress      = 56
IE_destinationMacAddress = 80
IE_flowStartMilliseconds = 152
IE_flowEndMilliseconds   = 153
IE_flowStartSeconds      = 150
IE_flowEndSeconds        = 151
IE_flowDirection         = 61
IE_sourceIPv6Address     = 27
IE_destinationIPv6Address = 28
IE_octetTotalCount       = 85
IE_packetTotalCount      = 86

# UniFi DPI uses some enterprise-specific elements; we accept them but
# don't decode unless the spec is documented.

VARIABLE_LENGTH = 0xFFFF


@dataclass
class TemplateField:
    ie: int
    length: int
    enterprise: int = 0  # 0 = IANA standard


@dataclass
class Template:
    template_id: int
    fields: list[TemplateField]
    is_options: bool = False
    record_size: int = 0   # set after construction; 0 if any field is variable

    def __post_init__(self) -> None:
        if all(f.length != VARIABLE_LENGTH for f in self.fields):
            self.record_size = sum(f.length for f in self.fields)


@dataclass
class TemplateRegistry:
    """Templates are scoped per (exporter address, observation domain id)."""
    _by_key: dict[tuple[str, int, int], Template] = field(default_factory=dict)

    def put(self, exporter: str, domain: int, tpl: Template) -> None:
        self._by_key[(exporter, domain, tpl.template_id)] = tpl

    def get(self, exporter: str, domain: int, template_id: int) -> Template | None:
        return self._by_key.get((exporter, domain, template_id))


# ----------------------------- Parser -------------------------------------

class ParseError(Exception):
    pass


def _u16(b: bytes, off: int) -> int:
    return struct.unpack_from("!H", b, off)[0]


def _u32(b: bytes, off: int) -> int:
    return struct.unpack_from("!I", b, off)[0]


def _read_int(b: bytes, off: int, length: int) -> int:
    if length <= 0 or off + length > len(b):
        raise ParseError("int overflow")
    return int.from_bytes(b[off:off + length], "big", signed=False)


def _read_bytes(b: bytes, off: int, length: int) -> bytes:
    if length < 0 or off + length > len(b):
        raise ParseError("bytes overflow")
    return b[off:off + length]


def parse_packet(
    data: bytes,
    exporter_addr: str,
    registry: TemplateRegistry,
) -> tuple[list[dict[str, Any]], int]:
    """Parse one UDP datagram. Returns (records, parsed_bytes).
    `records` is a list of parsed data records (each a dict keyed by IE id).
    Templates encountered are registered into `registry` as a side effect.
    """
    if len(data) < 16:
        raise ParseError("short header")
    version = _u16(data, 0)
    if version not in (NETFLOW_V9, IPFIX):
        raise ParseError(f"unsupported version {version}")

    if version == IPFIX:
        # IPFIX header (RFC 7011 §3.1): version, length, exportTime, sequence,
        # observationDomainID — 16 bytes total.
        total_length = _u16(data, 2)
        export_time = _u32(data, 4)
        sequence    = _u32(data, 8)
        domain      = _u32(data, 12)
        cursor = 16
        end = min(total_length, len(data))
    else:
        # NetFlow v9 header: version, count, sysUpTime, unixSecs,
        # packageSequence, sourceID — 20 bytes.
        record_count = _u16(data, 2)
        sys_uptime  = _u32(data, 4)
        unix_secs   = _u32(data, 8)
        sequence    = _u32(data, 12)
        domain      = _u32(data, 16)
        cursor = 20
        end = len(data)
        export_time = unix_secs

    out: list[dict[str, Any]] = []

    while cursor + 4 <= end:
        set_id = _u16(data, cursor)
        set_len = _u16(data, cursor + 2)
        if set_len < 4 or cursor + set_len > end:
            log.debug("malformed set len=%d cursor=%d end=%d", set_len, cursor, end)
            break
        set_end = cursor + set_len
        set_off = cursor + 4

        if set_id in (SET_ID_TEMPLATE_V9, SET_ID_TEMPLATE_IPFIX):
            _parse_template_set(data, set_off, set_end, exporter_addr, domain, registry, ipfix=(version == IPFIX))
        elif set_id in (SET_ID_OPTIONS_TEMPLATE_V9, SET_ID_OPTIONS_TEMPLATE_IPFIX):
            # Options templates carry metadata about the exporter; we don't
            # ingest them, but we still need to register them so subsequent
            # data records that reference them are skipped cleanly.
            _parse_options_template(data, set_off, set_end, exporter_addr, domain, registry, ipfix=(version == IPFIX))
        elif set_id >= 256:
            tpl = registry.get(exporter_addr, domain, set_id)
            if tpl is None:
                # Template not yet seen — UDM normally sends them every
                # `Refresh Rate` packets (default 20). Drop these records;
                # next time around we'll have the template.
                pass
            elif tpl.is_options:
                pass
            else:
                _parse_data_set(data, set_off, set_end, tpl, out, export_time)
        # Reserved set IDs (4–255) are ignored.

        cursor = set_end

    return out, cursor


def _parse_template_set(
    data: bytes, off: int, end: int,
    exporter: str, domain: int,
    registry: TemplateRegistry, *, ipfix: bool,
) -> None:
    while off + 4 <= end:
        template_id = _u16(data, off)
        field_count = _u16(data, off + 2)
        if template_id == 0 and field_count == 0:
            break  # padding
        off += 4
        fields: list[TemplateField] = []
        for _ in range(field_count):
            if off + 4 > end:
                return
            ie = _u16(data, off)
            length = _u16(data, off + 2)
            off += 4
            enterprise = 0
            if ipfix and (ie & 0x8000):
                if off + 4 > end:
                    return
                enterprise = _u32(data, off)
                off += 4
                ie &= 0x7FFF
            fields.append(TemplateField(ie=ie, length=length, enterprise=enterprise))
        registry.put(exporter, domain, Template(template_id=template_id, fields=fields))


def _parse_options_template(
    data: bytes, off: int, end: int,
    exporter: str, domain: int,
    registry: TemplateRegistry, *, ipfix: bool,
) -> None:
    while off + 4 <= end:
        template_id = _u16(data, off)
        if template_id == 0:
            break
        if ipfix:
            field_count = _u16(data, off + 2)
            if off + 6 > end:
                return
            scope_count = _u16(data, off + 4)
            off += 6
            scope = scope_count
            non_scope = field_count - scope_count
        else:  # v9
            scope_field_len = _u16(data, off + 2)
            opt_field_len   = _u16(data, off + 4) if off + 6 <= end else 0
            off += 6
            scope = scope_field_len // 4
            non_scope = opt_field_len // 4
        fields: list[TemplateField] = []
        for _ in range(scope + non_scope):
            if off + 4 > end:
                return
            ie = _u16(data, off)
            length = _u16(data, off + 2)
            off += 4
            enterprise = 0
            if ipfix and (ie & 0x8000):
                if off + 4 > end:
                    return
                enterprise = _u32(data, off)
                off += 4
                ie &= 0x7FFF
            fields.append(TemplateField(ie=ie, length=length, enterprise=enterprise))
        registry.put(exporter, domain, Template(
            template_id=template_id, fields=fields, is_options=True,
        ))


def _parse_data_set(
    data: bytes, off: int, end: int, tpl: Template,
    out: list[dict[str, Any]], export_time: int,
) -> None:
    rec_size = tpl.record_size
    while True:
        record: dict[str, Any] = {"_export_time": export_time}
        start = off
        for f in tpl.fields:
            length = f.length
            if length == VARIABLE_LENGTH:
                if off + 1 > end:
                    return
                length = data[off]; off += 1
                if length == 255:
                    if off + 2 > end:
                        return
                    length = _u16(data, off); off += 2
            if off + length > end:
                return
            if f.ie == IE_sourceIPv4Address or f.ie == IE_destinationIPv4Address:
                ip_bytes = _read_bytes(data, off, length)
                record[f.ie] = ".".join(str(b) for b in ip_bytes[:4])
            elif f.ie in (IE_sourceMacAddress, IE_destinationMacAddress):
                mb = _read_bytes(data, off, length)
                record[f.ie] = ":".join(f"{b:02x}" for b in mb[:6])
            elif length <= 8:
                record[f.ie] = _read_int(data, off, length)
            else:
                record[f.ie] = _read_bytes(data, off, length)
            off += length
        if rec_size and (off - start) != rec_size:
            log.debug("record size mismatch tpl=%d expected=%d got=%d",
                      tpl.template_id, rec_size, off - start)
        out.append(record)
        if rec_size and off + rec_size > end:
            return
        if not rec_size and off >= end:
            return
        if off >= end - 3:  # padding
            return
