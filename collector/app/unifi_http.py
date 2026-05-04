"""Mirror of backend/app/services/unifi_http.py for the collector container.

ThreatFlow is observability-only. This httpx client refuses any non-GET/HEAD
request to UniFi targets, with a narrow exception for the three known login
paths. See the backend module for the full contract.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("unifi.http")

_LOGIN_PATHS = frozenset({"/api/auth/login", "/api/login", "/api/sso/v1/user/login"})
_CLOUD_HOST_SUFFIXES = ("ui.com", "ubnt.com", "unifi-network.com")


class UniFiReadOnlyViolation(RuntimeError):
    pass


def _is_unifi_host(host: str) -> bool:
    if not host:
        return False
    h = host.lower()
    if any(h == s or h.endswith("." + s) for s in _CLOUD_HOST_SUFFIXES):
        return True
    return True  # collector clients only ever target UniFi


def _read_only_request_hook(request: httpx.Request) -> None:
    method = request.method.upper()
    if method in ("GET", "HEAD"):
        return
    if not _is_unifi_host(request.url.host or ""):
        return
    if method == "POST" and request.url.path in _LOGIN_PATHS:
        return
    log.error("BLOCKED non-read-only UniFi call: %s %s", method, str(request.url))
    raise UniFiReadOnlyViolation(
        f"ThreatFlow is read-only against UniFi; refusing {method} to {request.url}"
    )


def make_client(*, base_url: str | None = None, verify: bool | str = True, timeout: float = 10) -> httpx.AsyncClient:
    kwargs: dict[str, Any] = {
        "verify": verify,
        "timeout": httpx.Timeout(timeout),
        "follow_redirects": True,
        "event_hooks": {"request": [_read_only_request_hook]},
        "headers": {"User-Agent": "threatflow-collector/1.0 (read-only observability)"},
    }
    if base_url:
        kwargs["base_url"] = base_url.rstrip("/")
    return httpx.AsyncClient(**kwargs)
