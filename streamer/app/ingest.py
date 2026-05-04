"""HTTP client that batches mapped rows and POSTs them to the backend's
admin-only cloudproxy ingest endpoint.

The streamer logs in once with admin credentials, caches the session JWT
in-memory, and reuses it until a 401 forces a re-auth.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from app.config import settings

log = logging.getLogger("streamer.ingest")


class _TokenStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._token: str | None = None
        self._fetched_at = 0.0

    def get(self, force_refresh: bool = False) -> str:
        # Refresh once per hour even without 401, plus on demand.
        with self._lock:
            if (
                not force_refresh
                and self._token
                and (time.time() - self._fetched_at) < 3300
            ):
                return self._token
            body = json.dumps({
                "email": settings.admin_email,
                "password": settings.admin_password,
            }).encode("utf-8")
            req = urlrequest.Request(
                settings.api_base.rstrip("/") + "/api/auth/login",
                data=body, method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urlrequest.urlopen(req, timeout=15) as r:
                if r.status >= 400:
                    raise RuntimeError(f"login failed: HTTP {r.status}")
                cookie_header = r.getheader("Set-Cookie", "")
            # Parse threatflow_session cookie out of Set-Cookie
            tok = ""
            for part in cookie_header.split(","):
                kv = part.strip().split(";", 1)[0]
                if kv.startswith("threatflow_session="):
                    tok = kv.split("=", 1)[1]
                    break
            if not tok:
                raise RuntimeError("no threatflow_session cookie in login response")
            self._token = tok
            self._fetched_at = time.time()
            log.info("admin session refreshed")
            return tok


_tokens = _TokenStore()


def _serialize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        clean: dict[str, Any] = {}
        for k, v in r.items():
            if isinstance(v, datetime):
                if v.tzinfo is None:
                    v = v.replace(tzinfo=timezone.utc)
                clean[k] = v.isoformat()
            else:
                clean[k] = v
        out.append(clean)
    return out


def post_batch(branch_id: str, flow_rows: list[dict[str, Any]],
               threat_rows: list[dict[str, Any]]) -> tuple[int, int]:
    """POST a batch to the ingest endpoint. Returns (flows_inserted,
    threats_inserted). Raises on non-recoverable errors."""
    if not flow_rows and not threat_rows:
        return 0, 0
    payload = json.dumps({
        "branch_id":   branch_id,
        "flow_rows":   _serialize_rows(flow_rows),
        "threat_rows": _serialize_rows(threat_rows),
    }).encode("utf-8")
    url = settings.api_base.rstrip("/") + "/api/admin/ingest/cloudproxy"

    for attempt in (1, 2):
        token = _tokens.get(force_refresh=(attempt == 2))
        req = urlrequest.Request(
            url, data=payload, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        try:
            with urlrequest.urlopen(req, timeout=30) as r:
                body = r.read()
            data = json.loads(body)
            return int(data.get("flows_inserted", 0)), int(data.get("threats_inserted", 0))
        except urlerror.HTTPError as e:
            if e.code == 401 and attempt == 1:
                log.info("ingest got 401; refreshing token and retrying")
                continue
            err_body = e.read()[:300] if hasattr(e, "read") else b""
            raise RuntimeError(f"ingest failed HTTP {e.code}: {err_body!r}")
    raise RuntimeError("ingest failed after retries")
