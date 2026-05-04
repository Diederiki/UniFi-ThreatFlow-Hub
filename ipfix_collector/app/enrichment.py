"""Light-weight enrichment for IPFIX flows.

What we add at ingest time, on top of GeoIP-country:
  - Port-based application classification (HTTPS, DNS, RDP, SMB, etc.)
  - High-level application_category (web, email, file-transfer, ...)
  - Async reverse-DNS for non-internal destination IPs (cached, TTLed)

The reverse-DNS cache is in-process and bounded — entries expire after
30 minutes, and we never hold the listener loop on a hung lookup
(getaddrinfo runs in the default thread pool with a tight timeout).
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import time

log = logging.getLogger("ipfix.enrich")

# (proto, port) -> (application, category). Covers the bulk of normal
# traffic on a corporate UDM. Unknowns fall through to empty strings.
_APP_TABLE: dict[tuple[str, int], tuple[str, str]] = {
    ("tcp", 80):     ("http",       "web"),
    ("tcp", 443):    ("https",      "web"),
    ("tcp", 8080):   ("http-alt",   "web"),
    ("tcp", 8443):   ("https-alt",  "web"),
    ("udp", 53):     ("dns",        "dns"),
    ("tcp", 53):     ("dns-tcp",    "dns"),
    ("udp", 853):    ("dns-over-quic", "dns"),
    ("tcp", 853):    ("dns-over-tls",  "dns"),
    ("tcp", 22):     ("ssh",        "remote-access"),
    ("tcp", 23):     ("telnet",     "remote-access"),
    ("tcp", 3389):   ("rdp",        "remote-access"),
    ("tcp", 5900):   ("vnc",        "remote-access"),
    ("tcp", 5901):   ("vnc",        "remote-access"),
    ("tcp", 25):     ("smtp",       "email"),
    ("tcp", 465):    ("smtps",      "email"),
    ("tcp", 587):    ("submission", "email"),
    ("tcp", 110):    ("pop3",       "email"),
    ("tcp", 995):    ("pop3s",      "email"),
    ("tcp", 143):    ("imap",       "email"),
    ("tcp", 993):    ("imaps",      "email"),
    ("tcp", 21):     ("ftp",        "file-transfer"),
    ("tcp", 990):    ("ftps",       "file-transfer"),
    ("tcp", 989):    ("ftps-data",  "file-transfer"),
    ("tcp", 445):    ("smb",        "file-sharing"),
    ("tcp", 139):    ("netbios-ssn","file-sharing"),
    ("udp", 137):    ("netbios-ns", "file-sharing"),
    ("udp", 138):    ("netbios-dgm","file-sharing"),
    ("udp", 123):    ("ntp",        "time"),
    ("tcp", 123):    ("ntp-tcp",    "time"),
    ("udp", 161):    ("snmp",       "monitoring"),
    ("udp", 162):    ("snmp-trap",  "monitoring"),
    ("udp", 514):    ("syslog",     "logging"),
    ("tcp", 514):    ("syslog-tcp", "logging"),
    ("udp", 4789):   ("vxlan",      "tunneling"),
    ("udp", 1194):   ("openvpn",    "vpn"),
    ("udp", 51820):  ("wireguard",  "vpn"),
    ("udp", 4500):   ("ipsec-nat",  "vpn"),
    ("udp", 500):    ("ike",        "vpn"),
    ("udp", 1701):   ("l2tp",       "vpn"),
    ("tcp", 1723):   ("pptp",       "vpn"),
    ("tcp", 5060):   ("sip",        "voip"),
    ("udp", 5060):   ("sip",        "voip"),
    ("tcp", 5061):   ("sip-tls",    "voip"),
    ("tcp", 1935):   ("rtmp",       "streaming"),
    ("udp", 3478):   ("stun",       "webrtc"),
    ("udp", 3479):   ("stun",       "webrtc"),
    ("tcp", 3478):   ("turn-tcp",   "webrtc"),
    ("tcp", 3306):   ("mysql",      "database"),
    ("tcp", 5432):   ("postgres",   "database"),
    ("tcp", 1433):   ("mssql",      "database"),
    ("tcp", 1521):   ("oracle",     "database"),
    ("tcp", 6379):   ("redis",      "database"),
    ("tcp", 27017):  ("mongodb",    "database"),
    ("tcp", 9200):   ("elasticsearch","database"),
    ("tcp", 5672):   ("amqp",       "messaging"),
    ("tcp", 9092):   ("kafka",      "messaging"),
    ("tcp", 3000):   ("dev-server", "dev"),
    ("tcp", 8000):   ("dev-server", "dev"),
    ("tcp", 8888):   ("dev-server", "dev"),
    ("udp", 67):     ("dhcp",       "network-management"),
    ("udp", 68):     ("dhcp",       "network-management"),
    ("udp", 5353):   ("mdns",       "network-management"),
    ("udp", 1900):   ("ssdp",       "network-management"),
    ("udp", 67):     ("dhcp",       "network-management"),
    ("tcp", 6881):   ("bittorrent", "p2p"),
    ("udp", 6881):   ("bittorrent", "p2p"),
}


def classify_port(proto: str, port: int) -> tuple[str, str]:
    """(application, category) — empty strings if unknown."""
    if not port:
        return "", ""
    return _APP_TABLE.get((proto.lower(), int(port)), ("", ""))


# ----------------------------- Reverse DNS --------------------------------
# Small async-friendly cache. Each entry is (hostname, expires_at).
_DNS_CACHE: dict[str, tuple[str, float]] = {}
_DNS_TTL = 30 * 60  # seconds
_DNS_NEGATIVE_TTL = 5 * 60
_DNS_MAX_ENTRIES = 50_000
_DNS_LOOKUP_TIMEOUT = 1.0  # seconds — bounded so we never block ingestion


def _is_internal(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified


def _cache_get(ip: str) -> str | None:
    entry = _DNS_CACHE.get(ip)
    if not entry:
        return None
    name, expires = entry
    if time.time() > expires:
        del _DNS_CACHE[ip]
        return None
    return name


def _cache_put(ip: str, name: str, negative: bool = False) -> None:
    if len(_DNS_CACHE) >= _DNS_MAX_ENTRIES:
        # Evict ~10% of entries when we hit the cap, oldest first.
        ordered = sorted(_DNS_CACHE.items(), key=lambda kv: kv[1][1])[:_DNS_MAX_ENTRIES // 10]
        for k, _ in ordered:
            _DNS_CACHE.pop(k, None)
    _DNS_CACHE[ip] = (name, time.time() + (_DNS_NEGATIVE_TTL if negative else _DNS_TTL))


async def reverse_dns(ip_str: str) -> str:
    """Best-effort reverse DNS. Returns "" on internal/timeout/failure
    so the caller can stamp it directly on a row without checks."""
    if not ip_str or _is_internal(ip_str):
        return ""
    cached = _cache_get(ip_str)
    if cached is not None:
        return cached
    loop = asyncio.get_running_loop()
    try:
        info = await asyncio.wait_for(
            loop.run_in_executor(None, socket.gethostbyaddr, ip_str),
            timeout=_DNS_LOOKUP_TIMEOUT,
        )
        name = info[0] or ""
        _cache_put(ip_str, name)
        return name
    except (asyncio.TimeoutError, OSError, socket.herror):
        _cache_put(ip_str, "", negative=True)
        return ""
