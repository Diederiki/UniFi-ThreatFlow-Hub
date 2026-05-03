"""Single shared slowapi Limiter instance.

main.py registers this with the app + middleware. Route-level decorators
(@limiter.limit("10/minute")) must use the SAME instance to be honored, so
they import from here rather than constructing their own.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60/minute"] if settings.is_production else ["1000/minute"],
)
