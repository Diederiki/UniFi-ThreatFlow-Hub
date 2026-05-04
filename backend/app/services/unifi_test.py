"""Real Test-Connection + Discover-Sites for both UniFi flavours.

Detection:
  - Controller URL host matches *.ui.com / *.ubnt.com / api.ui.com → Cloud Site
    Manager API (https://api.ui.com/ea/sites with `X-API-KEY` header).
  - Anything else → Local UDM Pro / UXG. Two strategies tried in order:
      1. API-key against `/proxy/network/integration/v1/sites` (UniFi OS 4.x+)
      2. username/password against `/api/auth/login` then `/api/auth/login`-fallback
         then enumerate sites via `/proxy/network/api/self/sites`.

We always do a REAL probe — `MOCK_DATA` only governs event generation in the
collector, not config-time tests. That's why you got the MOCK badge before:
this file used to short-circuit when MOCK_DATA=true.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from app.models.branch import Branch
from app.schemas.branch import TestConnectionResult
from app.services.unifi_http import make_client
from app.utils.encryption import decrypt

log = logging.getLogger("unifi_test")

CLOUD_HOSTS = ("ui.com", "ubnt.com")  # match suffix
SITE_MANAGER_BASE = "https://api.ui.com"


def _is_cloud(controller_url: str) -> bool:
    try:
        host = (urlparse(controller_url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return False
    return any(host == h or host.endswith("." + h) for h in CLOUD_HOSTS)


def _decrypt_creds(branch: Branch) -> dict[str, str | None]:
    c = branch.credentials
    if c is None:
        return {"username": None, "password": None, "api_key": None, "token": None}
    return {
        "username": decrypt(c.encrypted_username),
        "password": decrypt(c.encrypted_password),
        "api_key":  decrypt(c.encrypted_api_key),
        "token":    decrypt(c.encrypted_token),
    }


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _extract_name(obj: dict) -> str | None:
    """Site Manager nests the human name in different places per object type.
    Walk the common ones and return the first non-empty string."""
    for key in ("name", "siteName", "hostName", "displayName"):
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # Console rows: name lives inside reportedState.hostname or .name
    rs = obj.get("reportedState") or {}
    if isinstance(rs, dict):
        for key in ("name", "hostname"):
            v = rs.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    meta = obj.get("meta") or {}
    if isinstance(meta, dict):
        for key in ("name", "displayName"):
            v = meta.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


async def _cloud_probe(api_key: str, started: float) -> TestConnectionResult:
    """Site Manager EA API. /ea/hosts has the human console names ("AmSpec-
    Dordrecht"); /ea/sites has the per-site UUIDs needed for the collector.
    We hit both and merge so the user sees readable names."""
    headers = {"X-API-KEY": api_key, "Accept": "application/json"}
    hosts_endpoint = f"{SITE_MANAGER_BASE}/ea/hosts"
    sites_endpoint = f"{SITE_MANAGER_BASE}/ea/sites"
    try:
        async with make_client(timeout=12) as client:
            hosts_resp, sites_resp = await asyncio.gather(
                client.get(hosts_endpoint, headers=headers),
                client.get(sites_endpoint, headers=headers),
            )
    except httpx.HTTPError as e:
        return TestConnectionResult(ok=False, endpoint_used=sites_endpoint, duration_ms=_ms(started),
                                    error=f"network_error: {type(e).__name__}: {e}")

    # Treat success as "either /hosts OR /sites returned 200" — the API key
    # might have host-only or site-only scope depending on its grant.
    hosts_ok = hosts_resp.status_code == 200
    sites_ok = sites_resp.status_code == 200
    if not (hosts_ok or sites_ok):
        body = (sites_resp.text or hosts_resp.text)[:300].replace("\n", " ")
        return TestConnectionResult(
            ok=False, endpoint_used=sites_endpoint, duration_ms=_ms(started),
            error=f"http_hosts={hosts_resp.status_code}_sites={sites_resp.status_code}: {body}",
        )

    names: list[str] = []
    seen: set[str] = set()

    if hosts_ok:
        try:
            for h in (hosts_resp.json().get("data") or []):
                if not isinstance(h, dict):
                    continue
                name = _extract_name(h)
                if name and name not in seen:
                    seen.add(name); names.append(name)
        except Exception:  # noqa: BLE001
            pass

    # Append site UUIDs that don't already appear (named consoles preferred)
    if sites_ok:
        try:
            site_count = 0
            for s in (sites_resp.json().get("data") or []):
                if not isinstance(s, dict):
                    continue
                site_count += 1
                # Prefer human name; fall back to internalReference (often "default")
                # and finally the raw site UUID
                name = _extract_name(s) or s.get("internalReference") or s.get("siteId") or s.get("id")
                if name and name not in seen:
                    seen.add(str(name)); names.append(str(name))
        except Exception:  # noqa: BLE001
            pass

    return TestConnectionResult(
        ok=True, endpoint_used=f"{hosts_endpoint} + {sites_endpoint}",
        duration_ms=_ms(started),
        sites_discovered=names[:100],
        is_mock=False,
    )


async def _local_api_key_probe(controller_url: str, api_key: str, ssl_verify: bool, started: float) -> TestConnectionResult | None:
    """Try the UniFi OS integration v1 API. Returns None if the endpoint is
    absent (404/405) so the caller can fall back to user/pass."""
    base = controller_url.rstrip("/")
    endpoint = f"{base}/proxy/network/integration/v1/sites"
    try:
        async with make_client(timeout=10, verify=ssl_verify) as client:
            r = await client.get(endpoint, headers={"X-API-KEY": api_key, "Accept": "application/json"})
    except httpx.HTTPError as e:
        return TestConnectionResult(ok=False, endpoint_used=endpoint, duration_ms=_ms(started),
                                    error=f"network_error: {type(e).__name__}: {e}")

    if r.status_code in (404, 405):
        return None  # endpoint not on this device — fall back to login flow

    if r.status_code == 401 or r.status_code == 403:
        return TestConnectionResult(ok=False, endpoint_used=endpoint, duration_ms=_ms(started),
                                    error=f"http_{r.status_code}: api key rejected")

    if r.status_code != 200:
        body = r.text[:300].replace("\n", " ")
        return TestConnectionResult(ok=False, endpoint_used=endpoint, duration_ms=_ms(started),
                                    error=f"http_{r.status_code}: {body}")

    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        return TestConnectionResult(ok=False, endpoint_used=endpoint, duration_ms=_ms(started),
                                    error="non_json_response")

    rows = data.get("data") or data
    if not isinstance(rows, list):
        rows = []
    sites: list[str] = []
    for s in rows:
        if not isinstance(s, dict):
            continue
        label = s.get("name") or s.get("desc") or s.get("internalReference") or s.get("id") or ""
        if label:
            sites.append(str(label))
    return TestConnectionResult(ok=True, endpoint_used=endpoint, duration_ms=_ms(started),
                                sites_discovered=sites[:100], is_mock=False)


async def _local_login_probe(controller_url: str, username: str, password: str, ssl_verify: bool, started: float) -> TestConnectionResult:
    base = controller_url.rstrip("/")
    last_err: str = ""
    async with make_client(timeout=10, verify=ssl_verify) as client:
        # Try newer UniFi OS path first, then legacy Network app
        for login_path in ("/api/auth/login", "/api/login"):
            url = f"{base}{login_path}"
            try:
                r = await client.post(url, json={"username": username, "password": password, "remember": True})
            except httpx.HTTPError as e:
                last_err = f"network_error on {login_path}: {type(e).__name__}: {e}"
                continue
            if r.status_code not in (200, 204):
                last_err = f"login {login_path}: http_{r.status_code}"
                continue

            # Logged in — enumerate sites
            for sites_path in (
                "/proxy/network/api/self/sites",     # UniFi OS
                "/api/self/sites",                   # legacy Network app
            ):
                try:
                    sr = await client.get(f"{base}{sites_path}")
                except httpx.HTTPError as e:
                    last_err = f"sites {sites_path}: {type(e).__name__}: {e}"
                    continue
                if sr.status_code != 200:
                    last_err = f"sites {sites_path}: http_{sr.status_code}"
                    continue
                try:
                    body = sr.json()
                except Exception:  # noqa: BLE001
                    last_err = f"sites {sites_path}: non_json"
                    continue
                rows = body.get("data") if isinstance(body, dict) else body
                sites: list[str] = []
                for s in (rows or []):
                    if not isinstance(s, dict):
                        continue
                    label = s.get("name") or s.get("desc") or s.get("_id") or ""
                    if label:
                        sites.append(str(label))
                return TestConnectionResult(
                    ok=True, endpoint_used=f"{login_path} → {sites_path}",
                    duration_ms=_ms(started), sites_discovered=sites[:100], is_mock=False,
                )
    return TestConnectionResult(ok=False, endpoint_used="local_login_flow",
                                duration_ms=_ms(started), error=last_err or "all login paths failed")


async def test_connection(branch: Branch, *, plaintext_creds: dict[str, Any] | None = None) -> TestConnectionResult:
    started = time.perf_counter()
    creds = _decrypt_creds(branch)
    api_key = creds["api_key"]
    username = creds["username"]
    password = creds["password"]

    if not branch.controller_url:
        return TestConnectionResult(ok=False, duration_ms=_ms(started), error="missing_controller_url")

    is_cloud = _is_cloud(branch.controller_url)

    if is_cloud:
        if not api_key:
            return TestConnectionResult(ok=False, duration_ms=_ms(started),
                                        error="cloud_url_requires_api_key (Site Manager → Admin → API Keys)",
                                        endpoint_used=f"{SITE_MANAGER_BASE}/ea/sites")
        return await _cloud_probe(api_key, started)

    # Local UDM
    if api_key:
        result = await _local_api_key_probe(branch.controller_url, api_key, branch.ssl_verify, started)
        if result is not None:
            return result
        # else fall through to login flow

    if username and password:
        return await _local_login_probe(branch.controller_url, username, password, branch.ssl_verify, started)

    return TestConnectionResult(
        ok=False, duration_ms=_ms(started),
        error="no_usable_credentials (need API key OR username+password)",
    )


async def discover_sites(branch: Branch, *, plaintext_creds: dict[str, Any] | None = None) -> TestConnectionResult:
    """Same wire-up as test_connection — both endpoints already discover sites."""
    return await test_connection(branch, plaintext_creds=plaintext_creds)
