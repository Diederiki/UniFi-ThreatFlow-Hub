"""Single shared slowapi Limiter instance.

main.py registers this with the app + middleware. Route-level decorators
(@limiter.limit("10/minute")) must use the SAME instance to be honored, so
they import from here rather than constructing their own.
"""
"""slowapi limiter, keyed on the real client IP behind nginx.

The default `slowapi.util.get_remote_address` reads `request.client.host`,
which is always `127.0.0.1` because uvicorn sees nginx, not the public IP.
That collapses every brute-force attempt into a single bucket — one attacker
can DoS legitimate logins, and per-IP limits are meaningless. We read the
left-most public IP from `X-Forwarded-For` instead, falling back to the
peer if the header is missing or malformed. Only use this with a trusted
reverse proxy (we do — nginx terminates TLS on the same host).
"""
from typing import Optional

from fastapi import Request
from slowapi import Limiter

from app.config import settings


def _trusted_client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        # Left-most entry is the original client; strip whitespace.
        first = fwd.split(",")[0].strip()
        if first:
            return first
    real = request.headers.get("x-real-ip", "").strip()
    if real:
        return real
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


limiter = Limiter(
    key_func=_trusted_client_ip,
    default_limits=["60/minute"] if settings.is_production else ["1000/minute"],
)
