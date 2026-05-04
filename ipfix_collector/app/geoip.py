"""GeoIP-country enrichment for IPFIX flows.

Loads a MaxMind GeoLite2-Country MMDB on startup, exposes a single
`country_for(ip)` function. RFC 1918 / link-local / loopback ranges
return an empty string so the dashboards' "Top Countries" view doesn't
get spammed with internal traffic.

If the MMDB is missing (download failed at build time) we degrade
gracefully — every lookup returns "" and a single warning is logged.
"""
from __future__ import annotations

import ipaddress
import logging
import os

log = logging.getLogger("ipfix.geoip")

_MMDB_PATH = os.environ.get("GEOIP_MMDB_PATH", "/app/data/GeoLite2-Country.mmdb")
_reader = None
_warned_missing = False


def _load() -> None:
    global _reader
    if _reader is not None:
        return
    try:
        import maxminddb
    except ImportError:
        log.warning("maxminddb not installed; geoip disabled")
        return
    if not os.path.exists(_MMDB_PATH):
        log.warning("geoip MMDB missing at %s; geoip disabled", _MMDB_PATH)
        return
    try:
        _reader = maxminddb.open_database(_MMDB_PATH)
        log.info("geoip MMDB loaded from %s", _MMDB_PATH)
    except Exception as e:
        log.warning("failed to open MMDB %s: %s — geoip disabled", _MMDB_PATH, e)


def _is_internal(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    if isinstance(ip, ipaddress.IPv4Address):
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified


def country_for(ip_str: str) -> str:
    """Return the ISO-3166 alpha-2 country code for ip_str, or "" for
    internal IPs / lookup failures."""
    global _warned_missing
    if not ip_str or _is_internal(ip_str):
        return ""
    if _reader is None:
        _load()
    if _reader is None:
        if not _warned_missing:
            _warned_missing = True
            log.warning("geoip lookup skipped — reader unavailable")
        return ""
    try:
        rec = _reader.get(ip_str)
        if not rec:
            return ""
        country = (rec.get("country") or {}).get("iso_code") or ""
        return country.upper()[:2]
    except Exception:
        return ""
