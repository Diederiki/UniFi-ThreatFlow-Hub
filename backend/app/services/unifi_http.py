"""Read-only HTTP client for every UniFi API call.

Hard contract: ThreatFlow Hub is observability-only. We never POST/PUT/PATCH/
DELETE anything to a UniFi controller or to api.ui.com — even by accident.

This module returns an `httpx.AsyncClient` with a request-event hook that
inspects every outbound request and raises `UniFiReadOnlyViolation` if the
method is anything other than GET or HEAD, with two narrow exceptions:

  - POST {controller}/api/auth/login        (UniFi OS local auth)
  - POST {controller}/api/login             (legacy Network app auth)
  - POST https://account.ui.com/api/sso/v1/user/login   (Ubiquiti SSO,
    only used by the username/password collector flow — not API-key flow)

Those three login paths only establish an authenticated session — they do
not change any network configuration. Everything else fails closed.

If a future contributor wants to add a write capability they will have to
edit this file deliberately, which is the audit trail we want.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

log = logging.getLogger("unifi.http")

# Exact-path POST whitelist. Anything else POST/PUT/PATCH/DELETE is blocked.
_LOGIN_PATHS = frozenset({
    "/api/auth/login",
    "/api/login",
    "/api/sso/v1/user/login",
})

# Hosts we treat as UniFi (cloud + Site Manager + Account SSO + ANY local
# controller — there's no good way to know "this isn't UniFi" so we apply the
# guard universally to any client built via this module).
_CLOUD_HOST_SUFFIXES = ("ui.com", "ubnt.com", "unifi-network.com")


class UniFiReadOnlyViolation(RuntimeError):
    """Raised when code tries to issue a write request through the
    read-only client. Treated as a security bug — never catch and continue."""


def _is_unifi_host(host: str) -> bool:
    if not host:
        return False
    h = host.lower()
    if any(h == s or h.endswith("." + s) for s in _CLOUD_HOST_SUFFIXES):
        return True
    # Local UDMs are LAN IPs / arbitrary hostnames; we can't tell from host
    # alone. The client is built per-branch, so we assume every host on a
    # client built here is a UniFi target.
    return True


async def _read_only_request_hook(request: httpx.Request) -> None:
    """Must be async — httpx.AsyncClient awaits its event-hook return values."""
    method = request.method.upper()
    if method in ("GET", "HEAD"):
        return
    if not _is_unifi_host(request.url.host or ""):
        return
    if method == "POST" and request.url.path in _LOGIN_PATHS:
        return  # narrow exception — auth only, no config change
    log.error(
        "BLOCKED non-read-only UniFi call: %s %s — ThreatFlow is observability-only",
        method, str(request.url),
    )
    raise UniFiReadOnlyViolation(
        f"ThreatFlow is read-only against UniFi; refusing {method} to {request.url}"
    )


def make_client(*, base_url: str | None = None, verify: bool | str = True, timeout: float = 10) -> httpx.AsyncClient:
    """Build an httpx.AsyncClient that enforces the read-only contract on
    every request. Always use this in unifi_test.py and the collector
    adapters — never construct httpx.AsyncClient directly for UniFi calls."""
    kwargs: dict[str, Any] = {
        "verify": verify,
        "timeout": httpx.Timeout(timeout),
        "follow_redirects": True,
        "event_hooks": {"request": [_read_only_request_hook]},
        "headers": {"User-Agent": "threatflow-hub/1.0 (read-only observability)"},
    }
    if base_url:
        kwargs["base_url"] = base_url.rstrip("/")
    return httpx.AsyncClient(**kwargs)
